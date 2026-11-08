import argparse
import csv
import math
import statistics
import sys


def summarize(rows, expected):
    if len(rows) != expected or {int(r['iter']) for r in rows} != set(range(expected)):
        raise ValueError('raw CSV must contain each expected iteration exactly once')
    allowed = {'ok', 'fail', 'timeout'}
    if any(r['status'] not in allowed for r in rows):
        raise ValueError('unknown measurement status')
    ok = [r for r in rows if r['status'] == 'ok']
    fields = ['hct_ms', 'sent_pkts', 'sent_bytes', 'recv_pkts', 'recv_bytes']
    values = {f: [float(r[f]) for r in ok] for f in fields}
    if any(not math.isfinite(v) or v < 0 for col in values.values() for v in col):
        raise ValueError('successful measurements must be finite and nonnegative')
    if any(v <= 0 for v in values['hct_ms']):
        raise ValueError('successful handshake duration must be positive')
    stats = ([statistics.median(values['hct_ms'])] + [statistics.mean(values[f]) for f in fields[1:]]) if ok else [''] * 5
    return stats + [len(ok), len(rows) - len(ok), sum(r['status'] == 'timeout' for r in rows)]


def main():
    parser = argparse.ArgumentParser(description="Summarize qamp's raw CSV without treating missing measurements as zero.")
    parser.add_argument('csv_path')
    for flag in ['expected', 'certsize', 'actual', 'initial-size']:
        parser.add_argument('--' + flag, required=True, type=int)
    parser.add_argument('--group', required=True)
    args = parser.parse_args()
    if args.expected <= 0:
        parser.error('expected must be positive')
    try:
        with open(args.csv_path, encoding='utf-8', newline='') as source:
            stats = summarize(list(csv.DictReader(source)), args.expected)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    csv.writer(sys.stdout, lineterminator='\n').writerow([args.certsize, args.group, *stats, args.actual, args.initial_size, 50, 'both'])


if __name__ == '__main__':
    main()
