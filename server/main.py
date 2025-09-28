import itertools
import pickle
import time
from typing import Generator, Iterator
from socket_server import Connection, SocketServer

class Action:
    MD5 = 'MD5'
    SHA256 = 'SHA256'

MAX_TASK_SIZE = int(0.2 * 1024 * 1024)  # 0.2 MB

class Task:
    def __init__(self, input_buffer: list, action: Action, expected_result: any):
        self.input_buffer = input_buffer
        self.action = action
        self.expected_result = expected_result
        self.id = id(self)
    
    @staticmethod
    def get_chunks(
        data_gen: Generator,
        total_size: int,
        chunk_count: int,
        action: Action,
        expected_result: any,
        max_chunk_size: int = -1
    ) -> tuple[Generator, int]:
    
        if chunk_count <= 0: chunk_count = 1

        if total_size // chunk_count > max_chunk_size:
            chunk_count = total_size // max_chunk_size
                
        base_chunk_size = total_size // chunk_count
        print(f"Dividing {total_size} items into {chunk_count} chunks of ~{base_chunk_size} items each")

        def _gen() -> Iterator[Task]:
            for i in range(chunk_count):
                chunk = []
                target_size = base_chunk_size + (total_size % chunk_count if i == chunk_count - 1 else 0)
                while len(chunk) < target_size:
                    try:
                        chunk.append(next(data_gen))
                    except StopIteration:
                        break
                if chunk:
                    yield Task(chunk, action, expected_result)

        return _gen(), chunk_count

class TaskOrchestrator:
    def __init__(self):
        self.callbacks = {
            "on_message": self.on_message,
            "on_disconnect": self.on_disconnect,
            "on_connect": self.on_connect
        }

        self.server = SocketServer(callbacks=self.callbacks)
        self.cores = []

        self.total_tasks = 0
        self.pending_tasks: Iterator[Task] = iter([])
        self.ongoing_tasks: dict[Connection, list[Task]] = {}
        self.finished_tasks = []
        self.start_time = 0
    
    def start(self):
        self.server.start()
    
    def add_tasks(self, tasks: Iterator[Task], tasks_len: int):
        self.total_tasks += tasks_len
        self.pending_tasks = itertools.chain(self.pending_tasks, tasks)

    def __send_task(self, connection: Connection, task: Task):
        exp = pickle.dumps(task.expected_result)
        connection.send_fields([
            'TASK',                                 # ID
            str(task.action),                       # Action
            str(task.id),                           # Unique Task ID
            str(len(exp)),                          # Expected Result Length
            exp,                                    # Expected Result
            pickle.dumps(task.input_buffer)         # Input Buffer
        ])

    def handle_tasks(self):
        self.start_time = time.time()
        index = 0
        while len(self.finished_tasks) != self.total_tasks:
            if not self.pending_tasks: continue
            
            connection = self.cores[index % len(self.cores)]

            task = next(self.pending_tasks, None)
            if task is None: continue
            self.ongoing_tasks[connection].append(task)
            self.__send_task(connection, task)
            index += 1
           

    def __finish_task(self, task_id: int):
        for conn, tasks in self.ongoing_tasks.items():
            for task in tasks:
                if task.id == int(task_id):
                    tasks.remove(task)
                    self.finished_tasks.append(task)
                    return

    def __reassign_task(self, task: Task):
        if task.id in self.ongoing_tasks:
            task, conn = self.ongoing_tasks.pop(task.id)
            self.pending_tasks.append(task)
            print(f"Task {task.id} reassigned from {conn}")

    def on_disconnect(self, conn: Connection):
        if conn in self.ongoing_tasks:
            self.cores = [c for c in self.cores if c != conn]
            tasks = self.ongoing_tasks.pop(conn)
            print(f"Connection {conn.addr} disconnected, reassigning {len(tasks)} tasks")
            for task in tasks:
                self.__reassign_task(task)

    def on_connect(self, conn: Connection):
        print(f"New connection established: {conn.addr}")
        conn.connect()
        self.ongoing_tasks[conn] = []
        self.cores.extend([conn] * conn.cores)

    def on_message(self, connection, raw, fields):
        if not fields or len(fields) < 2:
            print(f"Invalid message from {connection}: {fields}")
            return
        
        fields = connection._parse_fields(raw, 2)
        msg_id = fields[0].decode()
        if msg_id == 'FOUND':
            try:
                task_id = fields[1].decode()
                values = pickle.loads(fields[2])
                self.__finish_task(task_id)
                for value in values:
                    print(f"!!!! Task {task_id} found result: {value} (in {time.time() - self.start_time:.2f}s) !!!!")
            except Exception as e:
                print(f"Error processing FOUND message from {connection}: {e}")
        elif msg_id == 'DONE':
            try:
                task_id = fields[1].decode()
                self.__finish_task(task_id)
                print(f"Task {task_id} marked as DONE by {connection.addr[0]} (not found) {len(self.finished_tasks)}/{self.total_tasks}")
            except Exception as e:
                print(f"Error processing DONE message from {connection}: {e}")

if __name__ == "__main__":
    to = TaskOrchestrator()
    to.start()
    input("Press Enter to add tasks...\n")

    gen, chunk_count = Task.get_chunks(
        data_gen=(str(i) for i in range(100000000)), 
        total_size=100000000, 
        chunk_count=len(to.cores),
        action=Action.MD5,
        expected_result="ef775988943825d2871e1cfa75473ec0",
        max_chunk_size=MAX_TASK_SIZE
    )
    to.add_tasks(gen, chunk_count)
    to.handle_tasks()