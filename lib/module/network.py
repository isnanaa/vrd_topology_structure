import torch
import torch.nn as nn
from torch.autograd import Variable
import numpy as np
import torch.nn.init as init


class Conv2d(nn.Module):
	def __init__(self, in_channels, out_channels, kernel_size, stride=1, relu=True, same_padding=False, bn=False):
		super(Conv2d, self).__init__()
		padding = int((kernel_size - 1) / 2) if same_padding else 0
		self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding=padding)
		self.bn = nn.BatchNorm2d(out_channels, eps=0.001, momentum=0, affine=True) if bn else None
		self.relu = nn.ReLU(inplace=True) if relu else None
		
		# self.conv.weight.data.normal_(0, 0.01)
		init.normal_(self.conv.weight.data, 0, 0.01)
		init.constant_(self.conv.bias.data, 0)
		# self.conv.bias.data.zeros_()
	
	def forward(self, x):
		x = self.conv(x)
		if self.bn is not None:
			x = self.bn(x)
		if self.relu is not None:
			x = self.relu(x)
		return x


# class FC(nn.Module):
#     def __init__(self, in_features, out_features, relu=True):
#         super(FC, self).__init__()
#         self.fc = nn.Linear(in_features, out_features)
#         self.relu = nn.ReLU(inplace=True) if relu else None
#
#     def forward(self, x):
#         x = self.fc(x)
#         if self.relu is not None:
#             x = self.relu(x)
#         return x


def save_net(fname, net):
	import h5py
	h5f = h5py.File(fname, mode='w')
	for k, v in net.state_dict().items():
		h5f.create_dataset(k, data=v.cpu().numpy())


def load_net(fname, net):
	import h5py
	h5f = h5py.File(fname, mode='r')
	for k, v in net.state_dict().items():
		param = torch.from_numpy(np.asarray(h5f[k]))
		v.copy_(param)


def load_pretrained_RO_npy(faster_rcnn_model, fname):
	params = np.load(fname).item()
	# vgg16
	vgg16_dict = faster_rcnn_model.state_dict()
	for name, val in vgg16_dict.items():
		if name.find('bn.') >= 0 or not 'conv' in name or 'lo' in name:
			continue
		i, j = int(name[4]), int(name[6]) + 1
		ptype = 'weights' if name[-1] == 't' else 'biases'
		key = 'conv{}_{}'.format(i, j)
		param = torch.from_numpy(params[key][ptype])
		
		if ptype == 'weights':
			param = param.permute(3, 2, 0, 1)
		
		val.copy_(param)
	
	# fc6 fc7
	frcnn_dict = faster_rcnn_model.state_dict()
	pairs = {'fc6.fc': 'fc6', 'fc7.fc': 'fc7', 'fc6_obj.fc': 'fc6', 'fc7_obj.fc': 'fc7'}
	for k, v in pairs.items():
		key = '{}.weight'.format(k)
		param = torch.from_numpy(params[v]['weights']).permute(1, 0)
		frcnn_dict[key].copy_(param)
		
		key = '{}.bias'.format(k)
		param = torch.from_numpy(params[v]['biases'])
		frcnn_dict[key].copy_(param)


def load_pretrained_npy(faster_rcnn_model, fname):
	params = np.load(fname).item()
	# vgg16
	vgg16_dict = faster_rcnn_model.state_dict()
	for name, val in vgg16_dict.items():
		if name.find('bn.') >= 0 or not 'conv' in name or 'lo' in name:
			continue
		i, j = int(name[4]), int(name[6]) + 1
		ptype = 'weights' if name[-1] == 't' else 'biases'
		key = 'conv{}_{}'.format(i, j)
		param = torch.from_numpy(params[key][ptype])
		
		if ptype == 'weights':
			param = param.permute(3, 2, 0, 1)
		
		val.copy_(param)
	
	# fc6 fc7
	frcnn_dict = faster_rcnn_model.state_dict()
	pairs = {'fc6.fc': 'fc6', 'fc7.fc': 'fc7'}
	# pairs = {'fc6.fc': 'fc6', 'fc7.fc': 'fc7', 'fc7_so.fc': 'fc7'}
	for k, v in pairs.items():
		key = '{}.weight'.format(k)
		param = torch.from_numpy(params[v]['weights']).permute(1, 0)
		frcnn_dict[key].copy_(param)
		
		key = '{}.bias'.format(k)
		param = torch.from_numpy(params[v]['biases'])
		frcnn_dict[key].copy_(param)


def pretrain_with_det(net, det_model_path):
	det_model = torch.load(det_model_path)
	for k in det_model.keys():
		if ('rpn' in k or 'bbox' in k):
			del det_model[k]
	
	target_keys = []
	for k in net.state_dict().keys():
		if ('conv' in k):
			target_keys.append(k)
	
	for ix, k in enumerate(det_model.keys()):
		if ('features' in k):
			det_model[target_keys[ix]] = det_model[k]
			del det_model[k]
	
	det_model['fc6.fc.weight'] = det_model['vgg.classifier.0.weight']
	det_model['fc6.fc.bias'] = det_model['vgg.classifier.0.bias']
	det_model['fc7.fc.weight'] = det_model['vgg.classifier.3.weight']
	det_model['fc7.fc.bias'] = det_model['vgg.classifier.3.bias']
	det_model['fc_obj.fc.weight'] = det_model['cls_score_net.weight']
	det_model['fc_obj.fc.bias'] = det_model['cls_score_net.bias']
	
	for k in det_model.keys():
		if ('vgg' in k):
			del det_model[k]
	del det_model['cls_score_net.weight']
	del det_model['cls_score_net.bias']
	
	model_dict = net.state_dict()
	model_dict.update(det_model)
	net.load_state_dict(model_dict)


def np_to_variable(x, device, is_cuda=True, dtype=torch.FloatTensor):
	v = torch.from_numpy(x).type(dtype)
	if is_cuda:
		v = v.cuda(device=device)
	return v


def set_trainable(model, requires_grad):
	for param in model.parameters():
		param.requires_grad = requires_grad


def weights_normal_init(model, dev=0.01):
	if isinstance(model, list):
		for m in model:
			weights_normal_init(m, dev)
	else:
		for m in model.modules():
			if isinstance(m, nn.Conv2d):
				m.weight.data.normal_(0.0, dev)
			elif isinstance(m, nn.Linear):
				m.weight.data.normal_(0.0, dev)


def clip_gradient(model, clip_norm):
	"""Computes a gradient clipping coefficient based on gradient norm."""
	totalnorm = 0
	for p in model.parameters():
		if p.requires_grad:
			modulenorm = p.grad.data.norm()
			totalnorm += modulenorm ** 2
	totalnorm = np.sqrt(totalnorm)
	
	norm = clip_norm / max(totalnorm, clip_norm)
	for p in model.parameters():
		if p.requires_grad:
			p.grad.mul_(norm)


def input_tensor(im_data, boxes, rel_boxes, SpatialFea, classes_embed, ix1,
				 ix2, attr_boxes, obj_embeded, indices, device):
	""" data to cpu or gpu"""
	im_data = np_to_variable(im_data, device=device, is_cuda=True)
	# im_data = im_data.permute(0, 3, 1, 2)
	# (n,c,h,w)
	boxes = np_to_variable(boxes, device=device, is_cuda=True)
	rel_boxes = np_to_variable(rel_boxes, device=device, is_cuda=True)
	SpatialFea = np_to_variable(SpatialFea, device=device, is_cuda=True)
	classes_embed = np_to_variable(classes_embed, device=device, is_cuda=True)
	ix1 = np_to_variable(ix1, device=device, is_cuda=True, dtype=torch.LongTensor)
	ix2 = np_to_variable(ix2, device=device, is_cuda=True, dtype=torch.LongTensor)
	attr_boxes = np_to_variable(attr_boxes, device=device, is_cuda=True)
	obj_embeded = np_to_variable(obj_embeded, device=device, is_cuda=True)
	indices = np_to_variable(indices, device=device, is_cuda=True, dtype=torch.LongTensor)
	return im_data, boxes, rel_boxes, SpatialFea, classes_embed, ix1, ix2, attr_boxes, obj_embeded, indices
