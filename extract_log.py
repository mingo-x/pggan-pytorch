import argparse
import csv
import os
from parse import parse

parser = argparse.ArgumentParser(description='Parse training log')
parser.add_argument(
    '--log_file',
    default='',
    type=str,
    metavar='PATH',
    help='path to a training log file')
parser.add_argument(
	'--out_file',
	default='log.csv',
	type=str,
	metavar='PATH',
	help='Path to the output file.')
parser.add_argument(
	'--break',
	default=False,
	type=bool,
	help='Check where the training restarts.')

def main():
	args = parser.parse_args()
	if args.clean:
		prev_tick = 0
		with open(args.out_file, 'r') as fin:
			fin_reader = csv.reader(fin)
			row_idx = 0
			for row in fin_reader:
				row_idx += 1
				curr_tick = row[1]
				if prev_tick > curr_tick:
					print(row_idx, prev_tick, curr_tick)
				prev_tick = curr_tick
	else:
		log_pattern = " [E:{}][T:{}][{}/{}]  errD: {} | errG: {} | [lr:{}][cur:{}][resl:{}][{}][{}%][{}%]"
		with open(args.out_file, 'a+') as fout, open(args.log_file, 'r') as fin:
			fout_writer = csv.writer(fout)
			for in_line in fin:
				if not in_line.startswith(" [E:"):
					continue
				parsed_fields = list(parse(log_pattern, in_line))
				fout_writer.writerow(parsed_fields)

if __name__ == "__main__":
	main()
