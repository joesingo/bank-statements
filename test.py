from io import StringIO
from datetime import datetime
import operator

from bank import (NatwestReader, SantanderReader, Entry, get_statements,
                  AccountStatement, get_date_range, SortOrder)


d1 = datetime(year=2018, month=2, day=1)
d2 = datetime(year=2018, month=2, day=2)
d3 = datetime(year=2018, month=2, day=3)
d4 = datetime(year=2018, month=2, day=4)
d5 = datetime(year=2018, month=2, day=5)
d6 = datetime(year=2018, month=2, day=6)


class TestReaders(object):
    def test_natwest(self):
        lines = [
            "Date, Type, Description, Value, Balance, Account Name, Account Number",

            ('25/12/2017,TYPE,"\'Description, this is",-100.00,-200.05,'
             '"\'Account, name","\'012345",'),

            ('02/01/2018,TYPE,"\'Description, this is",50.04,-150.01,'
             '"\'Account, name","\'012345",'),

            "",

            ('01/01/2018,TYPE,"\'Description, this is",100.00,450.00,'
             '"\'My other account","\'999999",')
        ]
        f = StringIO()
        f.write("\n".join(lines))
        f.write("\n")
        f.seek(0)

        desc = "Description, this is"
        expected = [
            Entry(datetime(year=2017, month=12, day=25), -100.00, desc,
                  -200.05, "Account, name"),
            Entry(datetime(year=2018, month=1, day=2), 50.04, desc, -150.01,
                  "Account, name"),
            Entry(datetime(year=2018, month=1, day=1), 100.00, desc, 450.00,
                  "My other account")
        ]

        reader = NatwestReader(f)
        got = list(reader)
        assert got == expected

    def test_santander(self):
        f = StringIO()
        lines = [
            "From: 10/08/2017 to 10/02/2018",
            "",
            "Account: 12345678",
            "",
            "Date: 10/02/2018",
            "Description: Drink",
            "Amount: -1.50 ",
            "Balance: 101.55 ",
            "",
            "Date: 10/08/2017",
            "Description: Food",
            "Amount: -10.00 ",
            "Balance: 100.05 "
        ]
        f.write("\n".join(lines))
        f.write("\n")
        f.seek(0)

        expected = [
            Entry(datetime(year=2018, month=2, day=10), -1.5, "Drink", 101.55,
                  "Santander account"),
            Entry(datetime(year=2017, month=8, day=10), -10, "Food", 100.05,
                  "Santander account")
        ]

        reader = SantanderReader(f)
        got = list(reader)
        assert got == expected

    def test_get_statements(self):

        # Create a test reader class - needs to be iterable and have `order`
        # property
        class FakeReader(list):
            order = SortOrder.descending

        e1 = Entry(d6, 1, "d", 60, "acc 2")
        e2 = Entry(d4, 2, "d", 50, "acc 1")
        e3 = Entry(d2, 3, "d", 3, "acc 2")
        # Create two entries for d1 - since order is DESCENDING the balance
        # should be that of the FIRST one (e4)
        e4 = Entry(d1, 4, "d", 120, "acc 1")
        e5 = Entry(d1, 5, "d", 100, "acc 1")
        fake_reader = FakeReader([e1, e2, e3, e4, e5])

        expected = [
            AccountStatement("acc1", {
                d1: {"balance": 120, "entries": [e5, e4]},
                # Missing intermediate days should be present
                d2: {"balance": 120, "entries": []},
                d3: {"balance": 120, "entries": []},
                d4: {"balance": 50, "entries": [e2]},
            }),
            AccountStatement("acc2", {
                d2: {"balance": 3, "entries": [e3]},
                d3: {"balance": 3, "entries": []},
                d4: {"balance": 3, "entries": []},
                d5: {"balance": 3, "entries": []},
                d6: {"balance": 60, "entries": [e1]},
            })
        ]
        got = get_statements(fake_reader)

        # Sort as we do not care about the order of statements
        sort_key = operator.attrgetter("name")
        expected.sort(key=sort_key)
        got.sort(key=sort_key)

        assert got == expected

    def test_extend_balances(self):
        acc_st = AccountStatement("my account", {
            d1: {"balance": 100, "entries": []},
            d2: {"balance": 120, "entries": []}
        })
        acc_st.extend_balances(d5)
        assert acc_st == AccountStatement("my account", {
            d1: {"balance": 100, "entries": []},
            d2: {"balance": 120, "entries": []},
            d3: {"balance": 120, "entries": []},
            d4: {"balance": 120, "entries": []},
            d5: {"balance": 120, "entries": []}
        })

    def test_get_date_range(self):
        statements = [
            AccountStatement("acc 1", {
                d1: {"balance": 1, "entries": []},
                d2: {"balance": 2, "entries": []},
                d3: {"balance": 3, "entries": []},
            }),
            AccountStatement("acc 2", {
                d2: {"balance": 2, "entries": []},
                d3: {"balance": 3, "entries": []},
            }),
            AccountStatement("acc 3", {
                d2: {"balance": 2, "entries": []},
                d3: {"balance": 3, "entries": []},
                d4: {"balance": 3, "entries": []},
            })
        ]
        assert get_date_range(statements) == (d2, d4)
