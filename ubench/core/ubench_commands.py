# -*- coding: utf-8 -*-
##############################################################################
#  This file is part of the UncleBench benchmarking tool.                    #
#        Copyright (C) 2019 EDF SA                                           #
#                                                                            #
#  UncleBench is free software: you can redistribute it and/or modify        #
#  it under the terms of the GNU General Public License as published by      #
#  the Free Software Foundation, either version 3 of the License, or         #
#  (at your option) any later version.                                       #
#                                                                            #
#  UncleBench is distributed in the hope that it will be useful,             #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the              #
#  GNU General Public License for more details.                              #
#                                                                            #
#  You should have received a copy of the GNU General Public License         #
#  along with UncleBench. If not, see <http://www.gnu.org/licenses/>.        #
#                                                                            #
##############################################################################
# pylint: disable=superfluous-parens, fixme, invalid-name
""" Define UbenchCmd class """


import os
import re
from subprocess import Popen
import yaml

import ubench.core.ubench_config as uconfig
import ubench.benchmark_managers.benchmark_manager_set as bms
import ubench.benchmarking_tools_interfaces.jube_xml_parser as jube_xml_parser
import ubench.core.fetcher as fetcher
import ubench.data_management.comparison_writer as comparison_writer
import ubench.data_management.report as report

try:
    import ubench.scheduler_interfaces.slurm_interface as slurmi
except ImportError:
    pass


class UbenchCmd(object):
    """ Implements Unclebench commands.

    Each Unclebench command that can be calld from the command
    line is defined in this class.

    Attributes:
        log
        list_parameters
        result
        run
        fetch
        compare
        report
    """

    def __init__(self, platform, benchmark_list=None):
        """ Class constructor """

        self.uconf = uconfig.UbenchConfig()
        self.run_dir = os.path.join(self.uconf.run_dir, platform)
        self.platform = platform

        # Add benchmark managers for each benchmark in directory
        self.benchmark_list = benchmark_list
        self.bm_set = bms.BenchmarkManagerSet(benchmark_list, platform, self.uconf)


    def log(self, id_list=[-1]): # pylint: disable=dangerous-default-value
        """ Provides information about benchmark execution

        Args:
            id_list (optional): by default, it will print information on last
                                execution for the instance benchmark and platform.
        """
        for idb in id_list:
            self.bm_set.print_log(int(idb))


    def list_parameters(self, default_values=False):
        """ Lists benchmark parameters """

        self.bm_set.list_parameters(default_values)


    def result(self, id_list, debug_mode=None): # pylint: disable=dangerous-default-value
        """ Prints benchmark results """

        if id_list is None:
            id_list = ['last']

        for idb in id_list:
            self.bm_set.analyse(idb)
            self.bm_set.extract_results(idb)
            self.bm_set.print_result_array(debug_mode)


    def listb(self):
        """ Lists runs information"""

        self.bm_set.list_runs()


    def run(self, opt_dict={}):  # pylint: disable=dangerous-default-value
        """ TOCOMMENT """

        if opt_dict['w']:

            try:
                opt_dict['w'] = self.translate_wlist_to_scheduler_wlist(opt_dict['w'])
            except Exception as exc:  # pylint: disable=broad-except
                print('---- Custom node configuration is not valid : {0}'.format(str(exc)))
                return False
        print('')
        print('-- Ubench platform name set to : {0}'.format(self.platform))

        if not os.path.isdir(self.uconf.resource_dir):
            print('---- The resource directory {0} does not exist.'.
                  format(self.uconf.resource_dir) +
                  'Please run ubench fetch to retrieve sources and test cases.')
            return False

        # Set custom parameters
        dict_options = {}
        if opt_dict['file_params']:
            with open(opt_dict['file_params'], 'r') as params_file:
                dict_options = yaml.load(params_file)

            self.bm_set.set_parameter(dict_options)
            # we read a file which contains a dictionary with the options

        if opt_dict['custom_params']:
            for elem in opt_dict['custom_params']:
                try:
                    splitted_param = re.split(':', elem, 1)
                    dict_options[splitted_param[0]] = splitted_param[1]
                except Exception as exc:  # pylint: disable=broad-except
                    print('---- {0} is not formated correctly'.format(elem) +
                          ', please consider using : -c param:new_value')
                self.bm_set.set_parameter(dict_options)

        # Run each benchmarks
        self.bm_set.run(self.platform, opt_dict)
        return True

    def fetch(self):
        """ Fetches benchmarks sources """

        for benchmark_name in self.benchmark_list:
            benchmark_dir = os.path.join(self.uconf.benchmark_dir, benchmark_name)
            benchmark_files = [file_b for file_b in os.listdir(benchmark_dir)
                               if file_b.endswith(".xml")]
            jube_xml_files = jube_xml_parser.JubeXMLParser(benchmark_dir, benchmark_files)
            multisource = jube_xml_files.get_bench_multisource()

            if multisource is None:
                print("ERROR !! : Multisource information for benchmark not found")
                exit(1)

            fetch_bench = fetcher.Fetcher(resource_dir=self.uconf.resource_dir,
                                          benchmark_name=benchmark_name)
            for source in multisource:

                if 'do_cmds' not in source:
                    source['do_cmds'] = None

                if source['protocol'] == 'https':
                    fetch_bench.https(source['url'], source['files'])

                elif source['protocol'] == 'svn' or source['protocol'] == 'git':
                    if 'revision' not in source:
                        source['revision'] = None
                    if 'branch' not in source:
                        source['branch'] = None
                    fetch_bench.scm_fetch(source['url'], source['files'],
                                          source['protocol'], source['revision'],
                                          source['branch'], source['do_cmds'])

                elif source['protocol'] == 'local':
                    fetch_bench.local(source['files'], source['do_cmds'])


    # pylint: disable=no-self-use
    def compare(self, input_directories, benchmark_name, context=(None, None),
                threshold=None):
        """ Compare bencharks results from different directories.

        Args:
            input_directories:
            benchmark_name:
            context:
        """
        cwriter = comparison_writer.ComparisonWriter(threshold)
        print("    comparing :")
        for rdir in input_directories:
            print("    - "+rdir)
        print("")
        cwriter.print_comparison(benchmark_name, input_directories, context)


    def report(self, metadata_file, output_dir):
        """ Build a performance report.

        Args:
            metadata_file: file containing parameters for report build
            outpit_dir: where to store the report
        """
        bench_template = os.path.join(self.uconf.templates_path, "bench.html")
        compare_template = os.path.join(self.uconf.templates_path, "compare.html")
        report_template = os.path.join(self.uconf.templates_path, "report.html")
        perf_report = report.Report(metadata_file, bench_template,
                                    compare_template, report_template)
        report_name = "ubench_performance_report"

        print(("    Writing report {} in {} directory".format(report_name+".html", output_dir)))
        perf_report.write(output_dir, report_name)

        asciidoctor_cmd = ('asciidoctor -a stylesheet=' + self.uconf.stylesheet_path
                           + " " + os.path.join(os.getcwd(), output_dir, report_name + ".asc"))

        Popen(asciidoctor_cmd, cwd=os.getcwd(), shell=True, universal_newlines=True)


    # pylint: disable=undefined-loop-variable,too-many-locals
    def translate_wlist_to_scheduler_wlist(self, w_list_arg):
        """ Translate ubench custom node list format to scheduler custome node list format

        Args:
            w_list_arg:
        """

        try:
            scheduler_interface = slurmi.SlurmInterface()
        except:  # pylint:disable=bare-except
            print("Error!! Unable to load slurm module")
            scheduler_interface = None
            return None

        w_list = []
        for element in w_list_arg:
            if element.isdigit():
                elem_tuple = (int(element), None)
                w_list.append(elem_tuple)
            else:
                elem_tuple = (scheduler_interface.get_nnodes_from_string(element), element)
                w_list.append(elem_tuple)

        return w_list
