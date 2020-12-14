
import os,sys,time,random,uuid

from dpdispatcher.JobStatus import JobStatus
from dpdispatcher import dlog
class Batch(object) :
    def __init__ (self,
                  context):
        self.context = context

    def check_status(self, job) :
        raise NotImplementedError('abstract method check_status should be implemented by derived class')        
        
    def default_resources(self, res) :
        raise NotImplementedError('abstract method sub_script_head should be implemented by derived class')        

    def sub_script_head(self, res) :
        raise NotImplementedError('abstract method sub_script_head should be implemented by derived class')        

    def sub_script_cmd(self, res):
        raise NotImplementedError('abstract method sub_script_cmd should be implemented by derived class')        

    def do_submit(self, job):
        '''
        submit a single job, assuming that no job is running there.
        '''
        raise NotImplementedError('abstract method do_submit should be implemented by derived class')        

    def gen_script(self):
        raise NotImplementedError('abstract method gen_script should be implemented by derived class')        


pbs_script_template="""
{pbs_script_header}

{pbs_script_env}

{pbs_script_command}

{pbs_script_end}

"""

pbs_script_header_template="""
#!/bin/bash -l
{select_node_line}
{walltime_line}
#PBS -j oe
{queue_name_line}
"""

pbs_script_env_template="""
cd $PBS_O_WORKDIR
cd {job_work_base}
test $? -ne 0 && exit 1
"""

pbs_script_command_template="""

cd {task_work_path}
test $? -ne 0 && exit 1
if [ ! -f tag_0_finished ] ;then
  {command}  1>> {outlog} 2>> {errlog}
  if test $? -ne 0; then touch tag_0_failure; fi
  touch tag_0_finished
fi

"""

pbs_script_end_template="""
cd {job_work_base}
test $? -ne 0 && exit 1

wait
"""

class PBS(Batch):
    def gen_script(self, job):
        resources = job.resources
        script_header_dict= {}
        script_header_dict['select_node_line']="#PBS -l select={number_node}:ncpus={cpu_per_node}:ngpus={gpu_per_node}".format(
            number_node=resources.number_node, cpu_per_node=resources.cpu_per_node, gpu_per_node=resources.gpu_per_node)
        script_header_dict['walltime_line']="#PBS -l walltime=120:0:0"
        script_header_dict['queue_name_line']="#PBS -q {queue_name}".format(queue_name=resources.queue_name)

        pbs_script_header = pbs_script_header_template.format(**script_header_dict) 

        pbs_script_env = pbs_script_env_template.format(job_work_base=job.job_work_base)
      
        pbs_script_command = ""
        
        for task in job.job_task_list:
            temp_pbs_script_command = pbs_script_command_template.format(
                 task_work_path=task.task_work_path, command=task.command, outlog=task.outlog, errlog=task.errlog)
            pbs_script_command+=temp_pbs_script_command
        
        pbs_script_end = pbs_script_end_template.format(job_work_base=job.job_work_base)

        pbs_script = pbs_script_template.format(
                          pbs_script_header=pbs_script_header,
                          pbs_script_env=pbs_script_env,
                          pbs_script_command=pbs_script_command,
                          pbs_script_end=pbs_script_end)
        return pbs_script
    
    def do_submit(self, job):
        script_file_name = job.script_file_name
        script_str = self.gen_script(job)
        job_id_name = job.job_uuid + '_job_id'
        # script_str = self.sub_script(job_dirs, cmd, args=args, resources=resources, outlog=outlog, errlog=errlog)
        self.context.write_file(fname=script_file_name, write_str=script_str)
        stdin, stdout, stderr = self.context.block_checkcall('cd %s && %s %s' % (self.context.remote_root, 'qsub', script_file_name))
        subret = (stdout.readlines())
        job_id = subret[0].split()[0]
        self.context.write_file(job_id_name, job_id)        
        return job_id


    def default_resources(self, resources) :
        pass
    
    def check_status(self, job):
        job_id = job.job_id
        if job_id == "" :
            return JobStatus.unsubmitted
        ret, stdin, stdout, stderr\
            = self.context.block_call ("qstat " + job_id)
        err_str = stderr.read().decode('utf-8')
        if (ret != 0) :
            if str("qstat: Unknown Job Id") in err_str :
                if self.check_finish_tag() :
                    return JobStatus.finished
                else :
                    return JobStatus.terminated
            else :
                raise RuntimeError ("status command qstat fails to execute. erro info: %s return code %d"
                                    % (err_str, ret))
        status_line = stdout.read().decode('utf-8').split ('\n')[-2]
        status_word = status_line.split ()[-2]        
        # dlog.info (status_word)
        if status_word in ["Q","H"] :
            return JobStatus.waiting
        elif    status_word in ["R"] :
            return JobStatus.running
        elif    status_word in ["C","E","K"] :
            if self.check_finish_tag() :
                return JobStatus.finished
            else :
                return JobStatus.terminated
        else :
            return JobStatus.unknown
   


