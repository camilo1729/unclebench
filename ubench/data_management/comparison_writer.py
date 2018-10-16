#!/usr/bin/env python
# -*- coding: utf-8 -*-
##############################################################################
#  This file is part of the UncleBench benchmarking tool.                    #
#        Copyright (C) 2017  EDF SA                                          #
#                                                                            #
#  UncleBench is free software: you can redistribute it and/or modify        #
#  it under the terms of the GNU General Public License as published by      #
#  the Free Software Foundation, either version 3 of the License, or         #
#  (at your option) any later version.                                       #
#                                                                            #
#  UncleBench is distributed in the hope that it will be useful,             #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#  GNU General Public License for more details.                              #
#                                                                            #
#  You should have received a copy of the GNU General Public License         #
#  along with UncleBench.  If not, see <http://www.gnu.org/licenses/>.       #
#                                                                            #
##############################################################################
import os
import pandas
import ubench.data_management.data_store_yaml as dsy

class ComparisonWriter:

    def __init__(self, threshold=None):
        """ Constructor """
        self.dstore = dsy.DataStoreYAML()
        self.threshold = threshold

    def print_comparison(self, input_directories, benchmark_name, context=(None,None)):
        """
        Print arrays comparating results found in different input directories
        """
        df_to_print = self.compare(input_directories,benchmark_name,context)

        for dframe in df_to_print:
            print("")
            with pandas.option_context('display.max_rows', None, 'display.max_columns', \
                                       None,'expand_frame_repr', False):
                print(dframe)

    def _compare_pandas(self,pandas_list,context=(None,None)):
        """
        Return a panda dataframe comparing multiple pandas with there result relative
        differences computed and added as a column.
        """
        panda_ref = pandas_list[0]
        # Check context
        for key_f in context[0]:
            if key_f not in panda_ref:
                print('    '+str(key_f)+\
                      ' is not a valid context field, valid context fields for given directories are:')
                for cfield in panda_ref:
                    print('     - '+str(cfield))
                    return "No result"

        result_columns_pre_merge = [ x for x in list(panda_ref.columns.values) if x not in context[0]]

        # Do all but last merges keeping the original result field name unchanged
        idx = 0
        pd_compare = panda_ref
        for pdr in pandas_list[1:-1]:
            pd_compare = pandas.merge(pd_compare, pdr, on=context[0], \
                                      suffixes=['', '_post_'+str(idx)])
            idx += 1

        # At last merge add a _pre suffix to reference result
        if len(pandas_list)>1:
            pd_compare = pandas.merge(pd_compare, pandas_list[-1], \
                                      on=context[0], suffixes=['_pre', '_post_'+str(idx)])
        else:
            pd_compare = panda_ref


        pd_compare_columns_list = list(pd_compare.columns.values)
        result_columns = [ x for x in pd_compare_columns_list if x not in context[0]]
        ctxt_columns_list = context[0]

        if "nodes" in ctxt_columns_list:
            ctxt_columns_list.insert(0, ctxt_columns_list.pop(ctxt_columns_list.index("nodes")))

        pd_compare = pd_compare[ctxt_columns_list+result_columns]

        pandas.options.mode.chained_assignment = None # avoid useless warning

        # Convert numeric columns to int or float
        for ccolumn in context[0]:
            try:
                pd_compare[ccolumn] = pd_compare[ccolumn].apply(lambda x: int(x))
            except:
                try:
                    pd_compare[ccolumn] = pd_compare[ccolumn].apply(lambda x: float(x))
                except:
                    continue

        # Add difference columns in % for numeric result columns
        diff_columns = []

        for rcolumn in result_columns_pre_merge:
            pre_column = rcolumn+'_pre'
            for i in range(0,len(pandas_list[1:])):
                post_column=rcolumn+'_post_'+str(i)
                try:
                    diff_column_name=rcolumn+'_diff_'+str(i)+'(%)'
                    pd_compare[diff_column_name]=((pd_compare[post_column].apply(lambda x: float(x))-pd_compare[pre_column].apply(lambda x: float(x)))*100)/pd_compare[pre_column].apply(lambda x: float(x))
                except:
                    continue
                else:
                    diff_columns.append(diff_column_name)

        # Remove rows with no difference above given threshold
        if self.threshold:
            # Add a column with max :
            pd_compare['max_diff'] = pd_compare[diff_columns].max(axis=1).abs()
            # Use it as a filter :
            pd_compare = pd_compare[ pd_compare.max_diff > float(self.threshold)]
            pd_compare.drop('max_diff', 1,inplace=True)

        pandas.options.mode.chained_assignment = 'warn' #reactivate warning
        return(pd_compare.sort_values(by=ctxt_columns_list).to_string(index=False))


    def compare(self, input_directories, benchmark_name, context_in=(None,None)):
        """
        compare results of each input directory, first directory is considered to contain
        reference results
        """
        pandas_list = []
        context = (None,None)
        sub_bench = None
        metadata = {}
        for input_dir in input_directories:
            metadata, current_panda, current_context, current_sub_bench\
                = self.dstore._dir_to_pandas(input_dir, benchmark_name, context=context_in)
            if current_panda.empty:
                continue
            pandas_list.append(current_panda)

            # Get intesection of all context fields found in data files
            if not context[0]:
                context = (set(current_context[0]), current_context[1])
            else:
                context = (set(context[0]).intersection(set(current_context[0])), current_context[1])

            if sub_bench and current_sub_bench!=sub_bench:
                return("Different sub benchs found: {} and {}. Cannot compare results.")\
                    .format(current_sub_bench,sub_bench)
            else:
                sub_bench = current_sub_bench

        if not pandas_list:
            return("No ubench results data found in given directories or not well-formated data")

        if all(panda.empty for panda in pandas_list):
            return("")

        # List sub_benchs
        if not sub_bench:
            sub_bench_list = [None]
            context = (list(context[0]), context[1])
        else:
            context = (list(context[0])+[sub_bench], context[1])
            sub_bench_list = pandas_list[0][sub_bench].unique().tolist()

        # Do a comparison for each sub_bench
        pandas_result_list = []
        for s_bench in sub_bench_list:
            pandas_list_sub = []
            if(s_bench):
                for df in pandas_list:
                    pandas_list_sub.append(df[df[sub_bench]==s_bench])
            else:
                pandas_list_sub = pandas_list

            pandas_result_list.append(self._compare_pandas(pandas_list_sub,context))

        return pandas_result_list