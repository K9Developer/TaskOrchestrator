import pickle
from task import Task, TaskHandler
from socket_client import SocketClient

class Worker:
    def __init__(self, host: str, port: int):
        self.client = SocketClient(host, port)
        
    def connect(self):
        self.client.connect()
        self.client.handshake()
    
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
                    TaskHandler.handle_task(task, self.task_finished)
            except KeyboardInterrupt:
                print("Worker shutting down.")
                break
            except Exception as e:
                print(f"Error receiving task: {e}")
                break

if __name__ == "__main__":
    worker = Worker('10.100.102.216', 8080)
    worker.connect()
    worker.accept_tasks()