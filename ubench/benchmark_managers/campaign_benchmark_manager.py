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
# pylint: disable=invalid-name
""" Define CampaignManager class. """

import yaml
import os
from datetime import datetime
from shutil import copy, copytree
from ubench.config import CAMPAIGN_DATE_FORMAT, BENCHMARK_API_CLASS
from ubench.core.ubench_config import UbenchConfig
import ubench.scheduler_interfaces.slurm_interface as slurmi
from pydoc import locate
import time

class CampaignManager(object):

    def __init__(self, campaign_file, pre_results_file = None):
        #Load YAML
        #Load previous results
        self.campaign = yaml.load(open(campaign_file,'r'),Loader=yaml.FullLoader)
        self.pre_results = None # yaml load (pre_results_file)
        self.benchmarks = {}
        self.benchmark_api = locate(BENCHMARK_API_CLASS)
        date_campaign = datetime.now().strftime(CAMPAIGN_DATE_FORMAT)
        self.campaign_dir = os.path.join(UbenchConfig().run_dir,
                                         "campaign-{}-{}".format(self.campaign['name'],
                                                                 date_campaign))
        self.exec_info = {}
        self.campaign_status = {}
        self.scheduler_interface = slurmi.SlurmInterface()
    def init_campaign(self):
        # create base directory
        try:
            os.makedirs(self.campaign_dir)
        except (OSError) as e:
            print("Error: Campaign directory exist!!")
            print(e)
            raise


        # create benchmark objects
        c_benchmarks = self.campaign['benchmarks']
        platform = self.campaign['platform']
        for b_name, values in c_benchmarks.items():
            self._init_bench_dir(b_name)
            self.benchmarks[b_name] = self.benchmark_api(b_name, platform)
            self.campaign_status[b_name] = {}
            self.campaign_status[b_name]['status'] = 'INIT'

    def _init_bench_dir(self, benchmark):
        """ Create and initialize run directory
        """
        benchmark_dir = os.path.join(self.campaign_dir, benchmark)
        src_dir = os.path.join(UbenchConfig().benchmark_dir, benchmark)
        print("---- Copying {} to {}".format(src_dir, benchmark_dir))
        try:
            copytree(src_dir, benchmark_dir, symlinks=True)
        except OSError:
            print("---- {} description files are already present in " \
                  "run directory and will be overwritten.".format(benchmark))



    def init_status_data(self):
        pass


    def init_job_info(self, benchmark):

        if 'num_jobs' not in self.campaign_status[benchmark]:
            j_job, _ = self.exec_info[benchmark]
            job_ids = j_job.job_ids
            self.campaign_status[benchmark]['num_jobs'] = len(job_ids)
            self.campaign_status[benchmark]['running_jobs'] = set(job_ids)
            self.campaign_status[benchmark]['status'] = 'RUNNING'

    def update_campaign_status(self):
        finish_states = ['COMPLETED', 'FAILED', 'CANCELLED']
        for b_name, values in self.exec_info.items():

            if self.campaign_status[b_name]['status']  != 'FINISHED':

                j_job, _ = values

                if j_job.jube_returncode is None:
                    self.campaign_status[b_name]['status'] = 'COMPILING'
                    # print("benchmark {} compiling".format(b_name))
                elif j_job.jube_returncode == 0:
                    self.init_job_info(b_name)
                    job_req = self.scheduler_interface.get_jobs_state(j_job.job_ids)
                    print("benchmark {} has jobs {}".format(b_name,job_req))
                    finished_jobs = set([job_n for job_n, job_s in job_req.items() if job_s in finish_states])
                    self.campaign_status[b_name]['running_jobs']-=finished_jobs

                    if not self.campaign_status[b_name]['running_jobs'] :
                        self.campaign_status[b_name]['status'] = 'FINISHED'

                    self.campaign_status[b_name]['jobs'] = []
                    for exec_dir, job_id in j_job.mapping.items():
                        self.campaign_status[b_name]['jobs'].append({'jube_dir' : exec_dir,
                                                                     'status' : job_req[job_id],
                                                                     'job_id' : job_id})


    def print_campaign_status(self):
        print("-"*80)
        width = 20
        columns = 5
        print_format="{{:^{0}}} ".format(width)*columns
        print(print_format.format("Benchmark",
                                  "Jube_dir",
                                  "Status",
                                  "Job",
                                  "Bench status"))
        print("-"*80)
        for b_name, values in self.campaign_status.items():
            if 'jobs' in values:
                for line in values['jobs']:
                #benchmark, jube_dir, status, job, result
                    print(print_format.format(b_name,
                                              line['jube_dir'],
                                              line['status'],
                                              line['job_id'],
                                              self.campaign_status[b_name]['status']))
            else:
                print(print_format.format(b_name,
                                          "",
                                          "COMPILING",
                                          "",""))

    def get_status(self):
        pass

    def non_finished(self):
        for info in self.campaign_status.values():
            if info['status'] != 'FINISHED':
                return True
        return False

    def run(self):
        # we launched all benchmarks
        c_benchmarks = self.campaign['benchmarks']
        for b_name, values in c_benchmarks.items():
            print("Executing benchmark: {}".format(b_name))
            self.exec_info[b_name] = self.benchmarks[b_name].run(values['parameters'])


        while self.non_finished():
        # we loop over all benchmarks
            self.update_campaign_status()
            for b_name, values in self.exec_info.items():
                if self.campaign_status[b_name]['status'] == 'RUNNING':
                    total_jobs = self.campaign_status[b_name]['num_jobs']
                    r_jobs = self.campaign_status[b_name]['running_jobs']
                    print("benchmark {} running jobs {}".format(b_name,r_jobs))
                    if total_jobs > r_jobs:
                        print("Generating result file")
                        self.benchmarks[b_name].result()

            self.print_campaign_status()
            time.sleep(2)

        self.print_campaign_status()
        print("Campaign finished successfully")
