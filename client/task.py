import multiprocessing
import hashlib
import psutil

class Task:
    def __init__(self, action: str, id: int, expected_result, input_buffer):
        self.action = action
        self.id = id
        self.expected_result = expected_result
        self.input_buffer = input_buffer

class TaskHandler:
    cores_used = 0
    running_processes = []

    @staticmethod
    def cpu_compute_task(core: int, task: Task, callback: callable):
        hash_func = hashlib.md5 if task.action == "MD5" else hashlib.sha256 if task.action == "SHA256" else lambda x: None
        for item in task.input_buffer:
            if hash_func(item.encode()).hexdigest() == task.expected_result:
                callback(task.id, "found", [item])
                return
           
        callback(task.id, "done", [])

    @staticmethod
    def handle_task(task: Task, callback: callable):
        core_count = multiprocessing.cpu_count()
        core_index = TaskHandler.cores_used % core_count
        TaskHandler.cores_used += 1
        print(f"Processing task {task.id} with action {task.action} on input of size {len(task.input_buffer)} on core {core_index}")
        p = multiprocessing.Process(target=TaskHandler.cpu_compute_task, args=(core_index, task, callback))
        p.start()
        TaskHandler.running_processes.append(p)