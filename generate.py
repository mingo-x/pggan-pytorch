import os
import torch
from config import config
from torch.autograd import Variable
import utils as utils


use_cuda = True
checkpoint_path = '/srv/glusterfs/xieya/pytorch/repo/model/gs_R6_T5250.pth.tar'
n_intp = 50
max_resl = 2

torch.manual_seed(1000)

# load trained model.
import network as net
test_model = net.Generator(config)
if use_cuda:
    torch.set_default_tensor_type('torch.cuda.FloatTensor')
    test_model = torch.nn.DataParallel(test_model).cuda(device=0)
else:
    torch.set_default_tensor_type('torch.FloatTensor')

for resl in range(3, max_resl+1):
    test_model.module.grow_network(resl)
    test_model.module.flush_network()
print(test_model)


print('load checkpoint form ... {}'.format(checkpoint_path))
checkpoint = torch.load(checkpoint_path)
test_model.module.load_state_dict(checkpoint['state_dict'])


# create folder.
for i in range(1000):
    name = 'repo/generate/try_{}'.format(i)
    if not os.path.exists(name):
        os.system('mkdir -p {}'.format(name))
        print(name)
        break;

if use_cuda:
    test_model = test_model.cuda()

for i in range(1, n_intp+1):
    z = torch.FloatTensor(1, config.nz).normal_(0.0, 1.0)
    if use_cuda:
        z = z.cuda()

    z = Variable(z)
    fake_im = test_model.module(z)
    fname = os.path.join(name, '_gen{}.jpg'.format(i))
    utils.save_image_single(fake_im.data, fname, imsize=pow(2,max_resl))
    print('saved {}-th generated image ...'.format(i))







