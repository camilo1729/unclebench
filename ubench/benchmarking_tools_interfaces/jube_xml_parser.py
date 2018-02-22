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


import xml.etree.ElementTree as ET
import os
import re
import tempfile
import shutil

class JubeXMLParser():


  # There are three xml files that we need to load
  # - plattform
  # - bench
  # - config it is the xml generated by jube, we should load later after execution
  def __init__(self,bench_xml_path_in,bench_xml_files,bench_xml_path_out="",platforms_dir=""):
    self.bench_xml_path_in = bench_xml_path_in # string
    self.bench_xml_path_out = bench_xml_path_out # string
    self.bench_xml_files = bench_xml_files
    # I have to do a tuple here
    self.bench_xml = { xml_file : ET.parse(os.path.join(self.bench_xml_path_in,xml_file))  for xml_file in bench_xml_files}
    self.bench_xml_root = [bench_xml.getroot() for bench_xml in self.bench_xml.values()]
    self.platforms_dir = platforms_dir
    self.platform_dir = tempfile.mkdtemp()
    self.platform_xml = ""
    self.config_xml = ""

  def write_bench_xml(self):
    for name,xml_file in self.bench_xml.iteritems():
      xml_file.write(os.path.join(self.bench_xml_path_out,name))
    return True


  def delete_platform_dir(self):
    shutil.rmtree(self.platform_dir)

  def get_platform_dir(self):
    self.generate_platform()
    return self.platform_dir

  def remove_multisource(self):
    for b_xml in self.bench_xml_root:
      multisource = b_xml.find('multisource')
      if multisource is not None:
        b_xml.remove(multisource)

  def load_platforms_xml(self):
    self.generate_platform()
    return ET.parse(os.path.join(self.platform_dir,"platforms.xml")).getroot()

  # The file is loaded later on, when the benchmark has already been run
  def load_config_xml(self,path):
    self.config_xml = ET.parse(path).getroot()

  def get_bench_outputdir(self):
    for b_xml in self.bench_xml_root:
      benchmark_tag = b_xml.findall('benchmark')
      if benchmark_tag:
        return benchmark_tag[0].get('outpath')

  def get_bench_resultfile(self):
    for b_xml in self.bench_xml_root:
      bench_root = b_xml.find('benchmark')
      if bench_root is not None:
        result = bench_root.find("result")
        if result is not None:
          table = result.findall('table')
          if table is not None:
            return table[0].get('name')+".dat"
    return None

  def get_bench_steps(self):
    steps = []
    for b_xml in self.bench_xml_root:
      # either is on inside tag jube or tag benchmark
      bench_root = b_xml.find('benchmark')

      if bench_root is not None:
        steps+=[step.get('name') for step in bench_root.findall('step')]
      else:
        steps+=[step.get('name') for step in b_xml.findall('step')]

    return steps

  def get_bench_multisource(self):
    multisource_data = [] # [{'protocol': 'https'}, {'files' : ['file1','file2','file3']}, {'url': "http://ifjiaf"}, {'name' : "fa"}]
    for b_xml in self.bench_xml_root:
      multisource = b_xml.find('multisource')
      if multisource is not None:
        for source in multisource.findall('source'):
          source_dict = {}
          source_dict['protocol'] = source.get('protocol')
          source_dict['name'] = source.get('name')
          # file should be an array there could be many files for the benchmark
          source_dict['files'] = []
          for file_source in source.findall('file'):
            source_dict['files'].append(file_source.text.strip())

          source_dict['do_cmds'] = []
          for do_cmd in source.findall('do'):
            source_dict['do_cmds'].append(do_cmd.text.strip())

          if source.find('revision') is not None:
            source_dict['revision'] = []
            for revision_source in source.findall('revision'):
              source_dict['revision'].append(revision_source.text.strip())

          if source.find('url') is not None:
            source_dict['url'] = source.find('url').text
            if source_dict['protocol'] == 'git':
              source_dict['files']=[source_dict['url'].split('/')[-1].split('.')[0]]

          multisource_data.append(source_dict)

    return multisource_data

  def gen_bench_config(self):
    # bench_config is a dictionary of files and revision organized by protocol
    # {'svn': {'simple_code': ['tests_dir'], 'simple_code_revision': ['2018'], 'input_revision': ['1000'], 'input': ['file1', 'file2', 'file3']}}
    bench_config = {}
    multisource_data = self.get_bench_multisource()
    for source in multisource_data:
      protocol_config = {}
      name = source['name']
      protocol = source['protocol']
      for file_source in source['files']:
        if name:
          if not protocol_config.has_key(name):
                protocol_config[name] = []
          protocol_config[name].append(os.path.basename(file_source))

      if source.has_key('revision'):
        for revision_source in source['revision']:
          if name:
            name_revision=name+"_revision"
            if not protocol_config.has_key(name_revision):
              protocol_config[name_revision] = []
            protocol_config[name_revision].append(revision_source)

      if bench_config.has_key(protocol):
        bench_config[protocol].update(protocol_config)
      else:
        bench_config[protocol] = protocol_config

    return bench_config


  def get_params_bench(self):
    # include variable of multisource
    self.add_bench_input()
    parameters_list=[]
    for b_xml in self.bench_xml_root:
      for parameter_node in b_xml.getiterator('parameter'):
        parameters_list.append((parameter_node.get('name'),parameter_node.text.strip()))
    return parameters_list

  def set_params_bench(self,dict_options):
    # include variable of multisource
    self.add_bench_input()
    parameters_list=[]
    for b_xml in self.bench_xml_root:
      for parameter_node in b_xml.getiterator('parameter'):
        load_param = parameter_node.get('name')
        if  load_param in dict_options.keys():
          parameters_list.append((load_param,
                                  parameter_node.text.strip(),
                                  str(dict_options[load_param])))
          parameter_node.text=str(dict_options[load_param])
          upd=True

    return parameters_list

  def add_bench_input(self):
    # This method add automatically information concerning benchmark, input files obtained using the command fetch
    # bench_config is a dictionary {'svn' : {'bench_dir':["BENCH_F128_02","BENCH_F128_03"]},
    #                              {'http': {'code_sour' : faofaj}
    # Adding multisource files as JUBE variables
    bench_config = self.gen_bench_config()
    if not bench_config: # no information available
      return 0
    for b_xml in self.bench_xml_root:
      benchmark = b_xml.find('benchmark')

      if benchmark is not None:
        # if the element arlready exist we do nothing
        if benchmark.findall("parameterset[@name='ubench_config']"):
          return None

        config_element=ET.Element('parameterset',attrib={'name':'ubench_config'})
        benchmark.insert(0,config_element)
        # I have to insert this element into the main existing benchmark
        files_element=ET.Element('fileset',attrib={'name':'ubench_files'})
        benchmark.insert(1,files_element)
        benchmark_name = benchmark.get('name').lower()
        link = ET.SubElement(files_element,'link',attrib={'name': benchmark_name,'rel_path_ref': 'external'})
        link.text = "$UBENCH_RESOURCE_DIR/{0}/".format(benchmark_name)

        for protocol in bench_config.keys():
          # add another level

          for name,options in bench_config[protocol].iteritems():
            # if '-revision' in name:
            # Handling several revision
              # new_name = name.replace('-revision','')
            num_items = bench_config[protocol].keys()

            if ( protocol == 'svn' or protocol=='git') and not '_revision' in name and len(num_items)>1:
              name_id = name+'_id'
              custom_param = ET.SubElement(config_element,'parameter',attrib={'name': name_id})
              custom_param.text = ",".join(["{0}".format(x) for x in range(len(options))])

              custom_param = ET.SubElement(config_element,'parameter',
                                           attrib={'name':name, 'mode' : 'python'})
              revision_name = name+'_revision'

              new_paths = [ "${{{0}}}_{1}".format(revision_name,item)  for item in options]
              custom_param.text = str(new_paths)+"[${{{0}}}]".format(name_id)

            else:

              name_id = name+'_id'

              custom_param = ET.SubElement(config_element,'parameter',attrib={'name': name_id})
              custom_param.text = ",".join(["{0}".format(x) for x in range(len(options))])

              custom_param = ET.SubElement(config_element,'parameter',
                                         attrib={'name':name, 'mode' : 'python'})
              custom_param.text = str(options)+"[${{{0}}}]".format(name_id)


          # create link for benchmark directory
          for name,options in bench_config[protocol].iteritems():
            if not '_revision' in name:
              link = ET.SubElement(files_element,'link',attrib={'rel_path_ref': 'external'})
              if protocol == 'svn' or protocol == 'git':
                link.text = "$UBENCH_RESOURCE_DIR/{0}/{1}/${{{2}}}".format(benchmark_name.lower(),protocol,name)
              else:
                link.text = "$UBENCH_RESOURCE_DIR/{0}/${{{1}}}".format(benchmark_name.lower(),name)

      ### Adding special tags to step prepare
      if benchmark is None:
        step = b_xml.findall("step[@name='prepare']")
      else:
        step = benchmark.findall("step[@name='prepare']")

      if step: # not empty
        present_params = []
        for use in step[0].findall("use"):
          present_params.append(use.text)

        for name in ["ubench_config","ubench_files"]:
          use = ET.Element('use')
          use.text = name
          if name not in present_params:
            step[0].insert(0,use)


  def add_custom_nodes_stub(self,custom_nodes_numbers,custom_nodes_ids):
    """
    Comment TODO
    """
    found=False
    local_tree=None
    file_path=''

    # Add or modify custom nodes configuration section
    for b_xml in self.bench_xml_root:

      parents=self.get_parents_from_child_tag(b_xml,'step','execute')

      for p in parents:

        custom_element=ET.Element('parameterset',attrib={'name':'custom_parameter'})

        custom_id=ET.SubElement(custom_element,'parameter',\
                                  attrib={'name':'custom_id'})
        custom_id.text=(',').join(map(str,range(0,len(custom_nodes_numbers))))

        custom_nodes=ET.SubElement(custom_element,'parameter',\
                                     attrib={'name':'custom_nodes','mode':'python','type':'int'})
        custom_nodes.text=str(map(int,custom_nodes_numbers))+'[$custom_id]'

        if custom_nodes_ids:
          custom_nodes_id=ET.SubElement(custom_element,'parameter',\
                                        attrib={'name':'custom_nodes_id',\
                                                'mode':'python',\
                                                'type':'string',\
                                                'separator':'??'})
          custom_nodes_id.text=str(custom_nodes_ids)+'[$custom_id]'

          custom_submit=ET.SubElement(custom_element,'parameter',\
                                    attrib={'name':'custom_submit',\
                                            'separator':'??',\
                                            'mode':'python',\
                                            'type':'string',\
                                            'separator':'??'})

        if custom_nodes_ids:
          custom_submit.text='['
          for el in custom_nodes_ids:
            if el!=None:
              custom_submit.text+="'$submit -w $custom_nodes_id ',"
            else:
              custom_submit.text+="'$submit ',"
          custom_submit.text=custom_submit.text[:-1]+'][$custom_id]'

        p.insert(0,custom_element)


      # Add <use> custom_paremeters </use> in the appropriate section
      #for node in local_tree.iter('step'):
      for node in b_xml.getiterator('step'):
        local_found=False
        #for subnode in node.iter('use'):
        for subnode in node.getiterator('use'):
          if subnode.text=='custom_parameter':
            local_found=True
        if not local_found:
          update=True
          use_custom=ET.Element('use')
          use_custom.text='custom_parameter'
          node.insert(0,use_custom)

      # Add a node names column in result table
      # for node in local_tree.iter('table'):
      for node in b_xml.getiterator('table'):
        local_found=False
        for column in node.findall('column'):
          if column.text=='custom_nodes_id':
            local_found=True
            if not custom_nodes_ids:
              update=True
              node.remove(column)

        if not local_found and custom_nodes_ids:
          update=True
          custom_column=ET.Element('column')
          custom_column.text='custom_nodes_id'
          node.append(custom_column)


  def get_parents_from_child_tag(self,node,child_tag,child_name=None):
    result=[]

    if not list(node):
      return []

    for child in list(node):
      if child.tag==child_tag and (child.get('name')==child_name or not child_name):
        result.append(node)
      result=result+self.get_parents_from_child_tag(child,child_tag,child_name)

    return result


  def substitute_element_text(self,element,element_name,pattern,new_text):
    """
    subsitute pattern with new_text in the text from an xml node called element with attribute name
    element_name. The xml file is found in benchmark result root path.
    :param element: name of the xml node to be modified.
    :type element: str
    :param element_name: value of the 'name' attribute of the node to be modified.
    :type element_name: str
    :param pattern: pattern to be modified
    :type pattern: str
    """

    for b_xml in self.bench_xml_root:
      for el in b_xml.getiterator(element):
        if not element_name or el.get('name')==element_name:
          if re.findall(pattern,el.text):
            el.text=re.sub(pattern,new_text,el.text)

  def get_job_logfiles(self):
    config_xml_file = self.config_xml
    log_files = []
    for node in config_xml_file.getiterator('parameter'):
      if (node.get('name')=='outlogfile') or (node.get('name')=='errlogfile'):
        if node.text:
          log_files.append(node.text.strip())
    return log_files

  def get_analyse_files(self):
    config_xml_file = self.config_xml
    analyse_files = []
    for node in config_xml_file.getiterator('analyse'):
      for subnode in node.getiterator('file'):
        if subnode.text:
          analyse_files.append(subnode.text.strip())
    return analyse_files

  def get_dirs(self,dir_path):
    return [d for d in os.listdir(dir_path) if os.path.isdir(os.path.join(dir_path, d))]

  def generate_platform(self):
    platform_dir = self.platforms_dir

    template_xml = ET.parse(os.path.join(platform_dir,"template.xml")) # This contain the file platform.xml
    platform_directories = self.get_dirs(platform_dir)
    include_dir = template_xml.getroot().find("include-path")
    platform_element=ET.Element('path')
    platform_element.text = os.path.join(platform_dir)
    include_dir.insert(0,platform_element)

    for platform in platform_directories:
      subdirs = self.get_dirs(os.path.join(platform_dir,platform))
      if subdirs:
        # an element for the main directory
        platform_element=ET.Element('path',attrib={'tag': ",".join(subdirs)})
        platform_element.text = os.path.join(platform_dir,platform)
        include_dir.insert(0,platform_element)

        for subdir in subdirs:
          platform_element=ET.Element('path',attrib={'tag': subdir.lower()})
          platform_element.text = os.path.join(platform_dir,platform+"/"+subdir)
          include_dir.insert(0,platform_element)
      else:
        platform_element=ET.Element('path',attrib={'tag': platform.lower()})
        platform_element.text = os.path.join(platform_dir,platform)
        include_dir.insert(0,platform_element)

    template_xml.write(os.path.join(self.platform_dir,"platforms.xml"))



  def load_platform_xml(self,platform_name):
    platforms_xml = self.load_platforms_xml()
    path_raw = ""
    path_platform_xml = None
    for path in platforms_xml.iter('path'):
      if path.get('tag') == platform_name:
        path_raw = path.text
        for filetype in ["platform.xml","nodetype.xml"]:
          file = os.popen("echo "+os.path.join(path_raw,filetype)).read().strip()
          if os.path.exists(file):
            path_platform_xml = file

    if path_platform_xml:
      self.platform_xml = ET.parse(path_platform_xml).getroot()

  def get_params_platform(self):
    parameters_list=[]
    for parameter_node in self.platform_xml.getiterator('parameter'):
      if parameter_node.text:
        parameters_list.append((parameter_node.get('name'),parameter_node.text.strip()))
    return parameters_list
