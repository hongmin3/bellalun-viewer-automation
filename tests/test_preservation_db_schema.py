"""DB preservation must read the product's QC schedule schema before allowing a run.

Validates: REQ-FOLLOWUP-004. QC_SCHEDULE has QCType and ScheduleType, with no Key.
"""
import sqlite3
from types import SimpleNamespace

import pytest

from core.execution_session import DatabasePreservation


class ProductScheduleDatabase:
    def __init__(self, broken=False):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('CREATE TABLE QC_SCHEDULE (QCType int, ScheduleType int)')
        self.connection.executemany('INSERT INTO QC_SCHEDULE VALUES (?, ?)', [(3, 2), (1, 4), (1, 2)])
        self.broken = broken

    def query_many(self, specs):
        result = {item['name']: [] for item in specs}
        for item in specs:
            if item['name'] == 'qc_schedule':
                try:
                    if self.broken:
                        raise sqlite3.OperationalError('synthetic query failure')
                    result[item['name']] = [dict(row) for row in self.connection.execute(item['sql'])]
                except sqlite3.Error as error:
                    result[item['name']] = {'_error': str(error)}
        return result


def test_preservation_reads_all_qc_schedule_values_in_stable_order():
    adapter = DatabasePreservation(SimpleNamespace(db=ProductScheduleDatabase()))
    assert adapter._snapshot()['_sections']['qc_schedule'] == [
        {'QCType': 1, 'ScheduleType': 2},
        {'QCType': 1, 'ScheduleType': 4},
        {'QCType': 3, 'ScheduleType': 2},
    ]


def test_schedule_query_error_still_blocks_preservation():
    adapter = DatabasePreservation(SimpleNamespace(db=ProductScheduleDatabase(broken=True)))
    with pytest.raises(ValueError, match='DB 비교 범위'):
        adapter._snapshot()
