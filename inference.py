import torchvision.transforms as transforms
import torch
from config import config
import network as net
from PIL import Image
import os


def main():
	use_cuda = True
	checkpoint_path = '/srv/glusterfs/xieya/pytorch/repo/model/dis_R2_T300.pth.tar'
	img_dir = '/srv/glusterfs/xieya/dis/tf/'

	# load trained model.
	D = net.Discriminator(config)
	if use_cuda:
		torch.set_default_tensor_type('torch.cuda.FloatTensor')
		D = torch.nn.DataParallel(D).cuda(device=0)
	else:
		torch.set_default_tensor_type('torch.FloatTensor')

	for resl in range(3, config.max_resl+1):
		D.module.grow_network(resl)
		D.module.flush_network()
	print(D)

	print('load checkpoint form ... {}'.format(checkpoint_path))
	checkpoint = torch.load(checkpoint_path)
	D.module.load_state_dict(checkpoint['state_dict'])

	if use_cuda:
		D = D.cuda()

	transform = transforms.Compose([
		transforms.Resize(size=4, interpolation=Image.BILINEAR),
    	transforms.ToTensor()])

	for file_name in os.listdir(img_dir):
		img = Image.open(os.path.join(img_dir, file_name))
		img = transform(img).mul(2).add(-1)
		img = img.cuda()
		score = D(img)
		print(score)


if __name__ == "__main__":
	main()