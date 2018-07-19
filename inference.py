import pickle

from config import config


def main():
	pickle_path = config.restore_path
	image = 
	with open(pickle_path, 'rb') as fin:
		_, _, D = pickle.load(fin)
		dis_score = D(image)


if __name__ == '__main__':
	main()