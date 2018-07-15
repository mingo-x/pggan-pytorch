import argparse
import csv
from parse import parse

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

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
	'--breakpoint',
	default=False,
	type=bool,
	help='Check where the training restarts.')
parser.add_argument(
	'--plot',
	default=False,
	type=bool,
	help='Check where the training restarts.')

def main():
	args = parser.parse_args()
	if args.plot:
		with open(args.out_file, 'r') as fin:
			fin_reader = csv.reader(fin)
			row_idx = 0
			g_loss = []
			d_loss = []
			prev_resl = 4
			for row in fin_reader:
				row_idx += 1
				if int(row[8]) != prev_resl:
					print("Finish parsing data for resolution", prev_resl)
					plt.plot(d_loss)
					plt.savefig("d_loss_{}.png".format(prev_resl))
					plt.clf()
					print("D loss saved.")
					plt.plot(g_loss)
					plt.savefig("g_loss_{}.png".format(prev_resl))
					plt.clf()
					print("G loss saved.")
					g_loss = []
					d_loss = []
					prev_resl = int(row[8])
				d_loss.append(float(row[4]))
				g_loss.append(float(row[5]))

			print("Finish parsing data for resolution", prev_resl)
			plt.plot(d_loss)
			plt.savefig("d_loss_{}.png".format(prev_resl))
			plt.clf()
			print("D loss saved.")
			plt.plot(g_loss)
			plt.savefig("g_loss_{}.png".format(prev_resl))
			plt.clf()
			print("G loss saved.")	

	elif args.breakpoint:
		prev_tick = 0
		with open(args.out_file, 'r') as fin:
			fin_reader = csv.reader(fin)
			row_idx = 0
			for row in fin_reader:
				row_idx += 1
				curr_tick = int(row[1])
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
