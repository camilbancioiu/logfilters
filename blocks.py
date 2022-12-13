import re
import humanfriendly as H
from collections import Counter
from typing import Optional


class Block:
    def __init__(self, name, start_re, end_re):
        self.name = name
        self.start_re = re.compile(start_re)
        self.end_re = re.compile(end_re)
        self.at_start = False
        self.at_end = False
        self.started = False
        self.counter = 0

    def filter(self, line: str) -> Optional[str]:
        if self.keep(line):
            return self.modify(line)
        return None

    def keep(self, line):
        self.update(line)

        return self.at_start or self.at_end or self.started

    def modify(self, line: str) -> str:
        if self.at_start:
            return f'\n[{self.counter:>4}]\n' + line
        return line

    def update(self, line: str):
        self.at_start = False
        self.at_end = False

        if not self.started:
            if self.start_re.search(line) is not None:
                self.counter += 1
                self.started = True
                self.at_start = True

        if self.started:
            if self.end_re.search(line) is not None:
                self.started = False
                self.at_end = True


class BlockWithInstanceCounting(Block):
    def __init__(self, name, start_re, end_re):
        super().__init__(name, start_re, end_re)
        self.num_warm_instances_re = re.compile('warm = (-?[0-9]*)')
        self.num_cold_instances_re = re.compile('cold = (-?[0-9]*)')
        self.num_warm_instances = 0
        self.num_cold_instances = 0
        self.last_num_cold_instances = 0
        self.num_cold_instances_changed = False

    def filter(self, line: str) -> Optional[str]:
        self.read_num_instances(line)
        if self.keep(line):
            return self.modify(line)
        return None

    def update(self, line: str):
        super().update(line)
        self.read_num_instances(line)

        self.num_cold_instances_changed = False
        if self.at_end:
            if self.has_num_cold_instances_changed():
                self.num_cold_instances_changed = True
                self.update_num_instances()

    def modify(self, line: str) -> str:
        if self.at_end:
            if self.num_cold_instances_changed:
                return line + '  num cold instances changed' + '\n\n'
        return super().modify(line)

    def read_num_instances(self, line):
        if self.at_end:
            warm_match = self.num_warm_instances_re.search(line)
            cold_match = self.num_cold_instances_re.search(line)
            if warm_match is not None:
                self.num_warm_instances = int(warm_match[1])
            if cold_match is not None:
                self.num_cold_instances = int(cold_match[1])

    def has_num_cold_instances_changed(self):
        return self.num_cold_instances != self.last_num_cold_instances

    def update_num_instances(self):
        self.last_num_cold_instances = self.num_cold_instances


class BlockWithInstanceStats(BlockWithInstanceCounting):
    def __init__(self, name, start_re, end_re):
        super().__init__(name, start_re, end_re)

    def filter(self, line: str) -> Optional[str]:
        _ = super().filter(line)
        if self.at_end:
            c = self.counter
            warm = self.num_warm_instances
            cold = self.num_cold_instances
            return f'{c},{warm},{cold}\n'
        return None


class BlockWithNodeStats(Block):
    def __init__(self):
        super().__init__('node stats', '.', 'node statistics')
        self.setup_re()
        self.num_warm_instances = 0
        self.num_cold_instances = 0
        self.started_instances = Counter()
        self.round = 0
        self.sys_mem = 0
        self.heap_sys = 0
        self.heap_alloc = 0
        self.header_printed = False
        self.sys_mem_diff = 0

    def filter(self, line: str) -> Optional[str]:
        self.update(line)
        if self.at_end:
            stats = self.make_stats_line()
            if not self.header_printed:
                header = self.make_header()
                self.header_printed = True
                return header + stats
            else:
                return stats
        return None

    def update(self, line: str):
        super().update(line)
        if self.started:
            self.read_num_instances(line)
            self.read_started_instance(line)
            self.read_round(line)
        if self.at_end:
            self.read_node_stats(line)

    def make_stats_line(self) -> str:
        r = self.round
        w = self.num_warm_instances
        c = self.num_cold_instances
        sw = self.started_instances['warm']
        sc = self.started_instances['cached']
        sb = self.started_instances['bytecode']
        sm = self.sys_mem
        smd = self.sys_mem_diff
        hs = self.heap_sys
        ha = self.heap_alloc
        return f'{r},{w},{c},{sw},{sc},{sb},{sm},{smd},{hs},{ha}\n'

    def make_header(self) -> str:
        return ('round,warm-size,leaked-cold,started-warm,'
                'started-aotc,started-bytecode,'
                'sys-mem,sys-mem-diff,heap-sys,heap-alloc\n')

    def read_num_instances(self, line):
        if self.instances_line_re.search(line):
            warm_match = self.num_warm_instances_re.search(line)
            cold_match = self.num_cold_instances_re.search(line)
            if warm_match is not None:
                self.num_warm_instances = int(warm_match[1])
            if cold_match is not None:
                self.num_cold_instances = int(cold_match[1])

    def read_started_instance(self, line):
        match = self.start_instance_re.search(line)
        if match:
            instance_type = match[1]
            self.started_instances[instance_type] += 1

    def read_round(self, line):
        round_match = self.round_re.search(line)
        if round_match:
            self.round = int(round_match[1])

    def read_node_stats(self, line):
        new_sys_mem = H.parse_size(self.sys_mem_re.search(line)[1])
        self.sys_mem_diff = new_sys_mem - self.sys_mem
        self.sys_mem = new_sys_mem
        self.heap_sys = H.parse_size(self.heap_sys_re.search(line)[1])
        self.heap_alloc = H.parse_size(self.heap_alloc_re.search(line)[1])

    def setup_re(self):
        self.round_re = re.compile('committed.*round = ([0-9]*)')
        self.instances_line_re = re.compile('end instances')
        self.num_warm_instances_re = re.compile('warm = (-?[0-9]*)')
        self.num_cold_instances_re = re.compile('cold = (-?[0-9]*)')
        start_instance = 'start instance.*(warm|cached|bytecode)'
        self.start_instance_re = re.compile(start_instance)
        self.sys_mem_re = re.compile('sys mem = (.*) num GC')
        self.heap_sys_re = re.compile('heap sys = (.*) heap num')
        self.heap_alloc_re = re.compile('heap alloc = (.*) heap idle')
