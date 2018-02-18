from io import StringIO
from datetime import datetime
import operator

from bank import (HsbcCsvReader, NatwestReader, MidataReader, Entry,
                  get_statements, AccountStatement, get_date_range, SortOrder,
                  aggregate, is_week_start)


d1 = datetime(year=2018, month=2, day=1)
d2 = datetime(year=2018, month=2, day=2)
d3 = datetime(year=2018, month=2, day=3)
d4 = datetime(year=2018, month=2, day=4)
d5 = datetime(year=2018, month=2, day=5)
d6 = datetime(year=2018, month=2, day=6)


class FakeReader(list):
    """
    Test reader class - just needs to be iterable and have `order` property
    """
    order = SortOrder.descending


class TestReaders(object):
    def test_hsbc_csv_reader(self):
        lines = [
            '25/12/2017,My description here   VIS,"-50.65"',
            '20/12/2017,Other description   VIS,"25.00"',
            '20/10/2017,Other description   VIS,"-1,234.50"'
        ]
        f = StringIO()
        f.write("\n".join(lines))
        f.write("\n")
        f.seek(0)

        expected = [
            Entry(datetime(year=2017, month=10, day=20), -1234.50,
                  "Other description   VIS", -1234.50, "HSBC savings account"),

            Entry(datetime(year=2017, month=12, day=20), 25.00,
                  "Other description   VIS", -1209.50, "HSBC savings account"),

            Entry(datetime(year=2017, month=12, day=25), -50.65,
                  "My description here   VIS", -1260.15, "HSBC savings account")
        ]

        reader = HsbcCsvReader("HSBC savings account", f)
        got = list(reader)
        assert got == expected

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

        reader = NatwestReader("blah", f)
        got = list(reader)
        assert got == expected

    def test_midata_reader(self):
        lines = [
            "Date|Type|Merchant/Description|Debit/Credit|Balance|",
            "03/02/2018|CARD PAYMENT|CARD PAYMENT TO TESCO|-£3.01|£100.01|",
            "01/01/2018|OTHER TYPE|MONIES|+£400.71|£103.02|",
            "",
            "Arranged overdraft limit|03/02/2018|,+£0.00|"
        ]
        f = StringIO()
        f.write("\n".join(lines))
        f.write("\n")
        f.seek(0)

        expected = [
            Entry(datetime(year=2018, month=2, day=3), -3.01,
                  "CARD PAYMENT TO TESCO", 100.01, "my account"),
            Entry(datetime(year=2018, month=1, day=1), 400.71, "MONIES",
                  103.02, "my account")
        ]

        class MidataTestReader(MidataReader):
            delimiter = "|"
            account_name = "my account"

        reader = MidataTestReader("blah", f)
        got = list(reader)
        assert got == expected

    def test_get_statements(self):
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

    def test_aggregation(self):
        fri0 = datetime(year=2018, month=1, day=12)
        tues1 = datetime(year=2018, month=1, day=16)
        thurs1 = datetime(year=2018, month=1, day=18)
        sun1 = datetime(year=2018, month=1, day=21)
        mon2 = datetime(year=2018, month=1, day=22)
        wed2 = datetime(year=2018, month=1, day=24)
        wed4 = datetime(year=2018, month=2, day=7)

        e_list = [
            # Balance and account name are irrelevant here
            Entry(wed4, -7, "d", 0, "acc2"),

            Entry(wed2, -6, "d", 0, "acc1"),
            Entry(mon2, -5, "d", 0, "acc1"),

            Entry(sun1, -4, "d", 0, "acc2"),
            Entry(thurs1, -3, "d", 0, "acc1"),
            Entry(tues1, 100, "d", 0, "acc1"),  # Incoming money should be ignored
            Entry(tues1, -2, "d", 0, "acc2"),

            Entry(fri0, -1, "d", 0, "acc3")
        ]

        expected = [{
            "start": "08/01/18",
            "breakdown": {
                "spending": {
                    "total": 1,
                    "transactions": ["£1.00: d"]
                }
            }
        }, {
            "start": "15/01/18",
            "breakdown": {
                "spending": {
                    "total": 9,
                    "transactions": ["£2.00: d", "£3.00: d", "£4.00: d"]
                }
            }
        }, {
            "start": "22/01/18",
            "breakdown": {
                "spending": {
                    "total": 11,
                    "transactions": ["£5.00: d", "£6.00: d"]
                }
            }
        }, {
            "start": "29/01/18",
            "breakdown": {}
        }, {
            "start": "05/02/18",
            "breakdown": {
                "spending": {
                    "total": 7,
                    "transactions": ["£7.00: d"]
                }
            }
        }]

        got = aggregate(get_statements(FakeReader(e_list)), is_week_start,
                        fri0, wed4)
        assert got == expected
