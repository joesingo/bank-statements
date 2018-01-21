import csv
import os
import string
from datetime import datetime, timedelta


class Entry(object):
    def __init__(self, date, balance):
        self.date = date
        self.balance = balance


class SantanderReader(object):
    def __init__(self, f):
        for _ in range(3):
            f.readline()
        self.f = f

    def __iter__(self):
        return self

    def __next__(self):
        # Consume blank line or stop iteration
        if not self.f.readline():
            raise StopIteration

        date_line = self.f.readline().strip()
        date = datetime.strptime(date_line[6:], "%d/%m/%Y")

        # Consume amount and balance
        for _ in range(2):
            self.f.readline()

        balance_line = self.f.readline().strip()
        balance_str = "".join(c for c in balance_line if c in string.digits or c in (".", "-"))
        return Entry(date, float(balance_str))


class NatwestReader(object):
    def __init__(self, f):
        self.reader = csv.reader(f, delimiter=",")

    def __iter__(self):
        return self

    def __next__(self):
        date = None
        balance = None

        while True:
            row = next(self.reader)
            if not row:
                continue
            try:
                date = datetime.strptime(row[0], "%d/%m/%Y")
            except:
                continue

            balance = float(row[4])
            break

        return Entry(date, balance)


def parse(filename, reader_cls, open_kwargs):
    with open(filename, newline="", **open_kwargs) as f:
        reader = reader_cls(f)

        # Get valid entries in date ASCENDING order
        entries = [i for i in reader][::-1]
        prev_entry = entries[0]
        balances = {}

        for entry in entries[1:]:
            prev_date = prev_entry.date
            this_date = entry.date

            if this_date > prev_date:
                working_date = prev_date
                while working_date < this_date:
                    balances[working_date] = prev_entry.balance
                    working_date += timedelta(days=1)

            prev_entry = entry

        balances[prev_entry.date] = prev_entry.balance
        return balances


def extend_balances(balances, end_date):
    last_date = max(balances.keys())
    last_balance = balances[last_date]
    d = last_date + timedelta(days=1)
    while d <= end_date:
        balances[d] = last_balance
        d += timedelta(days=1)


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

    balances_list = {}
    for reader, config in reader_config.items():
        d = config["dir"]
        ext = ".{}".format(config["extension"])
        filelist = (os.path.join(d, f) for f in os.listdir(d) if f.endswith(ext))
        open_kwargs = config.get("open_kwargs", {})
        for filename in filelist:
            balances_list[filename] = parse(filename, reader, open_kwargs)

    # Work out earliest date for which balance is available in ALL accounts,
    # and max date for which data is available in AT LEAST ONE account
    start_dates_list = []
    end_dates_list = []
    for balances in balances_list.values():
        start_dates_list.append(min(balances.keys()))
        end_dates_list.append(max(balances.keys()))

    start_date = max(start_dates_list)
    end_date = max(end_dates_list)

    for balances in balances_list.values():
        extend_balances(balances, end_date)

    # Prin header row
    row = ["Date"]
    row += [os.path.basename(f) for f in balances_list.keys()]
    row.append("Total")
    print(",".join(row))

    d = start_date
    while d <= end_date:
        todays_balances = [balances[d] for balances in balances_list.values()]
        total = sum(todays_balances)

        row = [d.strftime("%d-%m-%Y")]
        row += [str(i) for i in todays_balances]
        row.append(str(total))
        print(",".join(row))

        d += timedelta(days=1)
