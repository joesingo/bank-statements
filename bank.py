import sys
import operator
from collections import namedtuple
import os
import string
from datetime import datetime, timedelta
from enum import Enum


Entry = namedtuple("Entry", ["date", "amount", "description", "balance",
                             "account_name"])


class AccountStatement(dict):
    """
    Thin wrapper over a dict to name dates to balance/entry list and store an
    account name
    """
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name

    def extend_balances(self, end_date):
        """
        Extend the balances recorded to include dates up to `end_date`
        """
        last_date = max(self.keys())
        last_balance = self[last_date]["balance"]
        d = last_date + timedelta(days=1)
        while d <= end_date:
            self[d] = {"balance": last_balance, "entries": []}
            d += timedelta(days=1)


class SortOrder(Enum):
    ascending = "asc"
    descending = "desc"


class StatementReader(object):
    """
    Class to read bank statements and return a list of AccountStatement objects
    for each account found in the statement
    """
    order = None  # Override in base class

    def __iter__(self):
        return self

    def __next__(self):
        raise NotImplementedError


class SantanderReader(StatementReader):

    order = SortOrder.descending

    def __init__(self, f):
        for _ in range(3):
            f.readline()
        self.f = f

    def __next__(self):
        # Consume blank line or stop iteration
        if not self.f.readline():
            raise StopIteration

        date_line = self.f.readline().strip()
        desc_line = self.f.readline().strip()
        amount_line = self.f.readline().strip()
        balance_line = self.f.readline().strip()

        date = datetime.strptime(date_line[6:], "%d/%m/%Y")
        description = desc_line[13:]
        return Entry(date, self.get_float(amount_line), description,
                     self.get_float(balance_line), "Santander account")

    def get_float(self, line):
        num_str = "".join(c for c in line
                          if c in string.digits or c in (".", "-"))
        return float(num_str)


class NatwestReader(StatementReader):

    # Entries are not strictly ascending in nw statements, but instead grouped
    # by account and then sorted ascending. Since we group entries by account
    # later, it is fine to say the ordering is ascending...
    order = SortOrder.ascending

    def __init__(self, f):
        self.file = f

    def split_outside_quotes(self, s, delim_char):
        """
        Split a string `s` by a single-character delimiter `delim_char`, but
        only when it appears outside double quotes
        """
        in_quotes = False
        parts = []
        temp = ""
        for char in s:
            if char == '"':
                in_quotes = not in_quotes
                continue

            if not in_quotes and char == delim_char:
                parts.append(temp)
                temp = ""
            else:
                temp += char
        parts.append(temp)
        return parts

    def __next__(self):
        date = None
        desc = None
        amount = None
        balance = None
        acc_name = None

        while True:
            line = self.file.readline()
            if not line:
                raise StopIteration

            line = line.strip()
            if not line:  # Skip blank lines
                continue

            row = self.split_outside_quotes(line.strip(), ",")
            for i, _ in enumerate(row):
                if row[i].startswith("'"):
                    row[i] = row[i][1:]

            date_str = row[0]
            description = row[2]
            amount_str = row[3]
            balance_str = row[4]
            acc_name = row[5]

            try:
                date = datetime.strptime(date_str, "%d/%m/%Y")
            except ValueError:
                continue

            amount = float(amount_str)
            balance = float(balance_str)
            break

        return Entry(date, amount, description, balance, acc_name)


def get_statements(reader):
    """
    Return a list of AccountStatement objects for entries retrieved from the
    given reader.

    The statement is returned such that every date in the range covered by the
    entry list is accounted for.
    """
    statements = {}  # Map acc. name to AccountStatement

    # Ensure entries are in ASCENDING date order
    entries = list(reader)
    if reader.order == SortOrder.descending:
        entries = entries[::-1]

    start_dates = {}
    end_dates = {}

    for e in entries:
        try:
            acc_st = statements[e.account_name]
        except KeyError:
            acc_st = AccountStatement(e.account_name)
            statements[e.account_name] = acc_st
            start_dates[e.account_name] = e.date

        if e.date not in acc_st:
            acc_st[e.date] = {"balance": None, "entries": []}

        # Overwrite balance to ensure that balance is that of the LAST entry
        # on a given day
        acc_st[e.date]["balance"] = e.balance
        acc_st[e.date]["entries"].append(e)

        # Override end date - since entries are sorted date ascending we will
        # always get the max in this way
        end_dates[e.account_name] = e.date

    # Fill in missing days
    for acc_name, acc_st in statements.items():
        d = start_dates[acc_name]
        prev_balance = None
        while d <= end_dates[acc_name]:
            if d in acc_st:
                prev_balance = acc_st[d]["balance"]
            else:
                acc_st[d] = {"balance": prev_balance, "entries": []}
            d += timedelta(days=1)

    return list(statements.values())


def get_date_range(statements):
    """
    Work out earliest date for which a balance is available in ALL accounts,
    and latest date for which data is available in AT LEAST ONE account.

    Return a tuple (start_date, end_date)
    """
    start_dates_list = []
    end_dates_list = []
    for acc_st in statements:
        start_dates_list.append(min(acc_st.keys()))
        end_dates_list.append(max(acc_st.keys()))

    return max(start_dates_list), max(end_dates_list)


def is_week_start(dt):
    return dt.weekday() == 0


def aggregate(statements, is_period_start, start_date, end_date):
    """
    Look at entries between `start_date` and `end_dates` in the
    AccountStatements in `statements`.

    Aggregate entries by week/month/etc (is_period_start(day) should be
    True iff day is the start of the time period) and categorise spending in
    each period.

    Return a list containing information for each time period of the form
    {
        "start": <start date as DD/MM/YY>,
        "breakdown": {
            "food": {"total": 20, "transactions": ["£10: Burger", ...]},
            "drink": {...}
            ...
        }
    }
    """
    aggregation = []
    period = None

    # Backtrack from start date to find start of period
    day = start_date
    while not is_period_start(day):
        day -= timedelta(days=1)

    while day <= end_date:
        if is_period_start(day):
            # Save previous period (if there was one) and reset
            if period is not None:
                aggregation.append(period)
            period = {"start": day.strftime("%d/%m/%y"), "breakdown": {}}

        for acc_st in statements:
            # Day may not be in statement if we had to backtrack to find period
            # start
            if day in acc_st:
                for e in acc_st[day]["entries"]:
                    cat = "spending"  # TODO: use description to get category
                    if cat not in period["breakdown"]:
                        period["breakdown"][cat] = {
                            "total": 0,
                            "transactions": []
                        }

                    # Only care about spending
                    if e.amount < 0:
                        period["breakdown"][cat]["total"] -= e.amount
                        transaction = "£{:.2f}: {}".format(-e.amount, e.description)
                        period["breakdown"][cat]["transactions"].append(transaction)

        day += timedelta(days=1)

    aggregation.append(period)
    return aggregation


def usage():
    prog = os.path.basename(sys.argv[0])
    usage = """Usage: {} [-s]

Read bank statements from subdirectories of 'statements' and produce an
aggregated statement in CSV format.

Options:
  -s, --spending    Print a weekly spending report instead of a statement
""".format(prog)
    print(usage)


if __name__ == "__main__":

    spending_report = False
    for arg in sys.argv[1:]:
        if arg in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif arg in ("-s", "--spending"):
            spending_report = True

    statements_dir = "statements"

    reader_config = {
        NatwestReader: {
            "dir": os.path.join(statements_dir, "natwest"),
            "extension": "csv"
        },
        SantanderReader: {
            "dir": os.path.join(statements_dir, "santander"),
            "extension": "txt",
            "open_kwargs": {"encoding": "ISO-8859-10"}
        }
    }

    statements = []
    for reader_cls, config in reader_config.items():
        d = config["dir"]
        ext = ".{}".format(config["extension"])
        filelist = (os.path.join(d, f) for f in os.listdir(d) if f.endswith(ext))
        open_kwargs = config.get("open_kwargs", {})
        for filename in filelist:
            with open(filename, newline="", **open_kwargs) as f:
                reader = reader_cls(f)
                statements += get_statements(reader)

    # Ensure all statements go up to the latest available date
    start_date, end_date = get_date_range(statements)
    for acc_st in statements:
        acc_st.extend_balances(end_date)

    if spending_report:
        aggregation = aggregate(statements, is_week_start, start_date, end_date)
        for period in aggregation:
            print("Week beginning {}:".format(period["start"]))
            for cat, breakdown in period["breakdown"].items():
                print("  {}: £{:.2f}".format(cat, breakdown["total"]))
                for tr in breakdown["transactions"]:
                    print("    {}".format(tr))

    else:
        # Sort alphabetically just for display purposes
        statements.sort(key=operator.attrgetter("name"))

        # Print header row
        row = ["Date"]
        row += map(operator.attrgetter("name"), statements)
        row.append("Total")
        print(",".join(row))

        d = start_date
        while d <= end_date:
            todays_balances = [acc_st[d]["balance"] for acc_st in statements]
            total = sum(todays_balances)

            row = [d.strftime("%d-%m-%Y")]
            row += map(str, todays_balances)
            row.append(str(total))
            print(",".join(row))

            d += timedelta(days=1)
