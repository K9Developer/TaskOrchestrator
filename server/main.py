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

    def _len_of_expanded_task(self, input_buffer) -> int:
        if type(input_buffer[0]) is str and "-" in input_buffer[0]:
            length = 0
            for item in input_buffer:
                start_str, end_str = item.split("-")
                start, end = int(start_str), int(end_str)
                length += (end - start)
            return length
        return len(input_buffer)

    def __send_task(self, connection: Connection, task: Task):
        print(f"Sending task {task.id} to {connection.addr[0]} ({len(task.input_buffer)} items)")
        connection.send_fields([
            'TASK',                                 # ID
            pickle.dumps(task),                     # Task object
        ])

    def handle_tasks(self):
        self.start_time = time.time()
        index = 0
        while len(self.finished_tasks) != self.total_tasks:
            if not self.pending_tasks or len(self.cores) == 0: continue
            
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
                    return task

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
        task_id = fields[1].decode()
        task = self.__finish_task(task_id)
        rate = 0
        time_took = time.time() - self.start_time
        if task:
            hashes_calculated = sum([self._len_of_expanded_task(t.input_buffer) for t in self.finished_tasks]) + self._len_of_expanded_task(task.input_buffer)
            rate = (hashes_calculated // time_took) if time_took > 0 else 0

        if msg_id == 'FOUND':
            
            try:
                values = pickle.loads(fields[2])
                for value in values:
                    print(f"Task {task_id} ({len(self.finished_tasks)}/{self.total_tasks}) marked as FOUND (value: {value}) by {connection.addr[0]} in {time_took:.2f}s, Rate: {rate} hashes/second")
            except Exception as e:
                print(f"Error processing FOUND message from {connection}: {e}")
        elif msg_id == 'DONE':
            print(f"Task {task_id} ({len(self.finished_tasks)}/{self.total_tasks}) marked as DONE by {connection.addr[0]} (not found), Rate: {rate} hashes/second")

if __name__ == "__main__":
    to = TaskOrchestrator()
    to.start()
    input("Press Enter to add tasks...\n\n")

    core_count = len(to.cores)
    max_num = 100_000_000
    
    chunk_size = max_num // core_count
    range_strings = []
    
    for i in range(core_count):
        start = i * chunk_size
        if i == core_count - 1:
            end = max_num
        else:
            end = (i + 1) * chunk_size
        range_strings.append(f"{start}-{end}")
    
    gen, chunk_count = Task.get_chunks(
        data_gen=(range_str for range_str in range_strings), 
        total_size=len(range_strings), 
        chunk_count=core_count,
        action=Action.MD5,
        expected_result="ef775988943825d2871e1cfa75473ec0",
        max_chunk_size=MAX_TASK_SIZE
    )
    print("Generated tasks, adding to orchestrator...\n")
    to.add_tasks(gen, chunk_count)
    to.handle_tasks()