import pickle
from task import Task, TaskHandler
from socket_client import SocketClient

class Worker:
    def __init__(self, host: str, port: int):
        self.client = SocketClient(host, port)
        
    def connect(self):
        self.client.connect()
        self.client.handshake()
    
    def _expand_task(self, task: Task):
        if type(task.input_buffer[0]) is not str or "-" not in task.input_buffer[0]: 
            return
        
        new_buff = []
        for item in task.input_buffer:
            start_str, end_str = item.split("-")
            start, end = int(start_str), int(end_str)
            new_buff.extend([str(i) for i in range(start, end)])
        task.input_buffer = new_buff

    def task_finished(self, task_id: int, status: str, values: list[any]):
        print(f"Task {task_id} finished with status: {status}, values: {values}")
        if status == "found":
            self.client.send_fields([
                'FOUND',              # ID
                str(task_id),         # Task ID
                pickle.dumps(values)  # Values
            ])
        elif status == "done":
            self.client.send_fields([
                'DONE',               # ID
                str(task_id)          # Task ID
            ])


    def accept_tasks(self):
        while True:
            try:
                data, fields = self.client.receive_fields(1)
                if not fields:
                    print("Connection closed by server")
                    break

                if fields[0] == b'TASK':
                    task = pickle.loads(fields[1])
                    self._expand_task(task)
                    TaskHandler.handle_task(task, self.task_finished)
            except KeyboardInterrupt:
                print("Worker shutting down.")
                break
            except Exception as e:
                print(f"Error receiving task: {e}")
                break

if __name__ == "__main__":
    worker = Worker('10.100.102.174', 8080)
    worker.connect()
    worker.accept_tasks()