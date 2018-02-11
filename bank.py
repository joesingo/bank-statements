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
    Thin wrapper over a dict to name dates to balances and store an account
    name
    """
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name

    def extend_balances(self, end_date):
        """
        Extend the balances recorded to include dates up to `end_date`
        """
        last_date = max(self.keys())
        last_balance = self[last_date]
        d = last_date + timedelta(days=1)
        while d <= end_date:
            self[d] = last_balance
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
    statements = []

    # Build a mapping acc_name to list of entries
    all_entries = {}
    for e in reader:
        if e.account_name not in all_entries:
            all_entries[e.account_name] = []
        all_entries[e.account_name].append(e)

    for acc_name, entries in all_entries.items():
        # Ensure entries are in ASCENDING date order
        if reader.order == SortOrder.descending:
            entries = entries[::-1]

        acc_statement = AccountStatement(acc_name)

        # Ensure that every day in range covered by entry list is
        # recorded in the statement
        prev_entry = entries[0]
        for entry in entries[1:]:
            prev_date = prev_entry.date
            this_date = entry.date

            if this_date > prev_date:
                working_date = prev_date
                while working_date < this_date:
                    acc_statement[working_date] = prev_entry.balance
                    working_date += timedelta(days=1)

            prev_entry = entry

        acc_statement[prev_entry.date] = prev_entry.balance
        statements.append(acc_statement)

    return statements


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


if __name__ == "__main__":
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

    # Sort alphabetically just for display purposes
    statements.sort(key=operator.attrgetter("name"))

    # Print header row
    row = ["Date"]
    row += map(operator.attrgetter("name"), statements)
    row.append("Total")
    print(",".join(row))

    d = start_date
    while d <= end_date:
        todays_balances = [acc_st[d] for acc_st in statements]
        total = sum(todays_balances)

        row = [d.strftime("%d-%m-%Y")]
        row += map(str, todays_balances)
        row.append(str(total))
        print(",".join(row))

        d += timedelta(days=1)
