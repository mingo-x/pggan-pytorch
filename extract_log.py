import argparse
import csv
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

def main():
	args = parser.parse_args()
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
