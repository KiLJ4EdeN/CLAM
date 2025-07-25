from __future__ import print_function

import argparse
import pdb
import os
import math

# internal imports
from utils.file_utils import save_pkl, load_pkl
from utils.utils import *
from utils.core_utils import train
from dataset_modules.dataset_generic import Generic_WSI_Classification_Dataset, Generic_MIL_Dataset

# pytorch imports
import torch
import pandas as pd
import numpy as np
import os
from glob import glob
import random
import torch
from torch.utils.data import Dataset
from PIL import Image
import numpy as np
from torchvision import transforms

class CLAM_MammoDataset(Dataset):
    def __init__(self, data_dir, split, seg_sess, pre_seg, cnn, pre_cnn,
                 feat_dim=1024, patch_size=64, overlap=0., coverage_thresh=0.5,
                 max_patches=None, shuffle=True, device='cpu'):

        self.seg = seg_sess
        self.pre_seg = pre_seg
        self.cnn = cnn.to(device).eval()
        self.pre_cnn = pre_cnn
        self.device = device
        self.feat_dim = feat_dim
        self.patch_size = patch_size
        self.stride = patch_size - int(overlap * patch_size)
        self.coverage_thresh = coverage_thresh
        self.max_patches = max_patches
        self.shuffle = shuffle

        self.data_dir = data_dir
        exts = ('.png', '.jpg', '.jpeg', '.tif', '.tiff')
        self.slides = sorted([
            p for p in glob(os.path.join(data_dir, 'images', split, '*.*'))
            if p.lower().endswith(exts)
        ])

    def __len__(self):
        return len(self.slides)

    def __getitem__(self, idx):
        path = self.slides[idx]

        # --- Infer label ---
        lbl_path = path.replace('images', 'labels').rsplit('.', 1)[0] + '.txt'
        label = 1 if os.path.exists(lbl_path) and os.path.getsize(lbl_path) > 0 else 0
        label = torch.tensor(label).long()

        # --- Load image ---
        img = Image.open(path).convert('RGB')
        gray = img.convert('L')
        w, h = gray.size

        # --- Skip bad slides ---
        if w >= h or (min(w, h) < 512 and max(w, h) < 1000):
            return torch.zeros((0, self.feat_dim)), label

        # --- Segmentation mask ---
        inp = self.pre_seg(gray).unsqueeze(0).numpy()
        out = self.seg.run(None, {'input': inp})[0]
        prob = torch.from_numpy(out[0])
        mask = (prob.sigmoid() > 0.5).float()
        mask = transforms.ToPILImage()(mask).resize((w, h), Image.NEAREST)
        mask = np.array(mask) > 0

        # --- Extract valid patch coords ---
        coords = [
            (x, y)
            for y in range(0, h - self.patch_size + 1, self.stride)
            for x in range(0, w - self.patch_size + 1, self.stride)
            if mask[y:y + self.patch_size, x:x + self.patch_size].mean() >= self.coverage_thresh
        ]
        if self.shuffle:
            random.shuffle(coords)
        if self.max_patches and len(coords) > self.max_patches:
            coords = coords[:self.max_patches]
        if not coords:
            return torch.zeros((0, self.feat_dim)), label

        # --- Patch and encode ---
        patches = [self.pre_cnn(img.crop((x, y, x + self.patch_size, y + self.patch_size))) for x, y in coords]
        batch = torch.stack(patches, dim=0).to(self.device)

        with torch.no_grad():
            features = self.cnn(batch)

        return features.cpu(), label


def main(args):
    # create results directory if necessary
    if not os.path.isdir(args.results_dir):
        os.mkdir(args.results_dir)

    if args.k_start == -1:
        start = 0
    else:
        start = args.k_start
    if args.k_end == -1:
        end = args.k
    else:
        end = args.k_end

    all_test_auc = []
    all_val_auc = []
    all_test_acc = []
    all_val_acc = []
    # folds = np.arange(start, end)
    # for i in folds:
    #     seed_torch(args.seed)
    #     train_dataset, val_dataset, test_dataset = dataset.return_splits(from_id=False, 
    #             csv_path='{}/splits_{}.csv'.format(args.split_dir, i))
        
    #     datasets = (train_dataset, val_dataset, test_dataset)
    #     results, test_auc, val_auc, test_acc, val_acc  = train(datasets, i, args)
    #     all_test_auc.append(test_auc)
    #     all_val_auc.append(val_auc)
    #     all_test_acc.append(test_acc)
    #     all_val_acc.append(val_acc)
    #     #write results to pkl
    #     filename = os.path.join(args.results_dir, 'split_{}_results.pkl'.format(i))
    #     save_pkl(filename, results)

    folds = np.arange(start, end)
    for i in folds:
        seed_torch(args.seed)
        # segmentation ONNX session
        import onnxruntime as ort
        from torchvision import transforms, models
        onnx_session = ort.InferenceSession(
            "/home/parsa/preprocessing-changes-object/mg-cancer-experimentation/clam/segmentation.onnx",
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        preprocess_for_onnx = transforms.Compose([
            transforms.Resize((256,256)),
            transforms.ToTensor(),
            transforms.Normalize([0.5],[0.5])
        ])

        # patch CNN
        cnn = models.resnet50(pretrained=True) # 18 cuz memory, 50 default
        feat_dim = cnn.fc.in_features
        cnn.fc = nn.Identity()
        cnn.eval().to(device)

        preprocess_for_cnn = transforms.Compose([
            transforms.Resize(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
        ])
        data_root_dir = '/home/parsa/preprocessing-changes-object/mg-cancer-experimentation/yolo_masks_nocbis_ncrop'
        train_dataset = CLAM_MammoDataset(
            data_dir=data_root_dir,
            split='training',
            seg_sess=onnx_session,
            pre_seg=preprocess_for_onnx,
            cnn=cnn,
            pre_cnn=preprocess_for_cnn,
            feat_dim=args.embed_dim,
            patch_size=64,
            overlap=0,
            coverage_thresh=0.5,
            max_patches=1000,
            shuffle=True,
            device=device
        )
        val_dataset = CLAM_MammoDataset(
            data_dir=data_root_dir,
            split='training',
            seg_sess=onnx_session,
            pre_seg=preprocess_for_onnx,
            cnn=cnn,
            pre_cnn=preprocess_for_cnn,
            feat_dim=args.embed_dim,
            patch_size=64,
            overlap=0,
            coverage_thresh=0.5,
            max_patches=1000,
            shuffle=True,
            device=device
        )
        
        datasets = (train_dataset, val_dataset, val_dataset)
        results, test_auc, val_auc, test_acc, val_acc  = train(datasets, i, args)
        all_test_auc.append(test_auc)
        all_val_auc.append(val_auc)
        all_test_acc.append(test_acc)
        all_val_acc.append(val_acc)
        #write results to pkl
        filename = os.path.join(args.results_dir, 'split_{}_results.pkl'.format(i))
        save_pkl(filename, results)

    final_df = pd.DataFrame({'folds': folds, 'test_auc': all_test_auc, 
        'val_auc': all_val_auc, 'test_acc': all_test_acc, 'val_acc' : all_val_acc})

    if len(folds) != args.k:
        save_name = 'summary_partial_{}_{}.csv'.format(start, end)
    else:
        save_name = 'summary.csv'
    final_df.to_csv(os.path.join(args.results_dir, save_name))

# Generic training settings
parser = argparse.ArgumentParser(description='Configurations for WSI Training')
parser.add_argument('--data_root_dir', type=str, default=None, 
                    help='data directory')
parser.add_argument('--embed_dim', type=int, default=1024)
parser.add_argument('--max_epochs', type=int, default=200,
                    help='maximum number of epochs to train (default: 200)')
parser.add_argument('--lr', type=float, default=1e-4,
                    help='learning rate (default: 0.0001)')
parser.add_argument('--label_frac', type=float, default=1.0,
                    help='fraction of training labels (default: 1.0)')
parser.add_argument('--reg', type=float, default=1e-5,
                    help='weight decay (default: 1e-5)')
parser.add_argument('--seed', type=int, default=1, 
                    help='random seed for reproducible experiment (default: 1)')
parser.add_argument('--k', type=int, default=10, help='number of folds (default: 10)')
parser.add_argument('--k_start', type=int, default=-1, help='start fold (default: -1, last fold)')
parser.add_argument('--k_end', type=int, default=-1, help='end fold (default: -1, first fold)')
parser.add_argument('--results_dir', default='./results', help='results directory (default: ./results)')
parser.add_argument('--split_dir', type=str, default=None, 
                    help='manually specify the set of splits to use, ' 
                    +'instead of infering from the task and label_frac argument (default: None)')
parser.add_argument('--log_data', action='store_true', default=False, help='log data using tensorboard')
parser.add_argument('--testing', action='store_true', default=False, help='debugging tool')
parser.add_argument('--early_stopping', action='store_true', default=False, help='enable early stopping')
parser.add_argument('--opt', type=str, choices = ['adam', 'sgd'], default='adam')
parser.add_argument('--drop_out', type=float, default=0.25, help='dropout')
parser.add_argument('--bag_loss', type=str, choices=['svm', 'ce'], default='ce',
                     help='slide-level classification loss function (default: ce)')
parser.add_argument('--model_type', type=str, choices=['clam_sb', 'clam_mb', 'mil'], default='clam_sb', 
                    help='type of model (default: clam_sb, clam w/ single attention branch)')
parser.add_argument('--exp_code', type=str, help='experiment code for saving results')
parser.add_argument('--weighted_sample', action='store_true', default=False, help='enable weighted sampling')
parser.add_argument('--model_size', type=str, choices=['small', 'big'], default='small', help='size of model, does not affect mil')
parser.add_argument('--task', type=str, choices=['task_1_tumor_vs_normal',  'task_2_tumor_subtyping'])
### CLAM specific options
parser.add_argument('--no_inst_cluster', action='store_true', default=False,
                     help='disable instance-level clustering')
parser.add_argument('--inst_loss', type=str, choices=['svm', 'ce', None], default=None,
                     help='instance-level clustering loss function (default: None)')
parser.add_argument('--subtyping', action='store_true', default=False, 
                     help='subtyping problem')
parser.add_argument('--bag_weight', type=float, default=0.7,
                    help='clam: weight coefficient for bag-level loss (default: 0.7)')
parser.add_argument('--B', type=int, default=8, help='numbr of positive/negative patches to sample for clam')
args = parser.parse_args()
device=torch.device("cuda" if torch.cuda.is_available() else "cpu")

def seed_torch(seed=7):
    import random
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device.type == 'cuda':
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed) # if you are using multi-GPU.
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

seed_torch(args.seed)

encoding_size = 1024
settings = {'num_splits': args.k, 
            'k_start': args.k_start,
            'k_end': args.k_end,
            'task': args.task,
            'max_epochs': args.max_epochs, 
            'results_dir': args.results_dir, 
            'lr': args.lr,
            'experiment': args.exp_code,
            'reg': args.reg,
            'label_frac': args.label_frac,
            'bag_loss': args.bag_loss,
            'seed': args.seed,
            'model_type': args.model_type,
            'model_size': args.model_size,
            "use_drop_out": args.drop_out,
            'weighted_sample': args.weighted_sample,
            'opt': args.opt}

if args.model_type in ['clam_sb', 'clam_mb']:
   settings.update({'bag_weight': args.bag_weight,
                    'inst_loss': args.inst_loss,
                    'B': args.B})

print('\nLoad Dataset')

args.n_classes=2
args.k = 1
args.k_start = 0
args.k_end = 1

# if args.task == 'task_1_tumor_vs_normal':
#     args.n_classes=2
#     dataset = Generic_MIL_Dataset(csv_path = 'dataset_csv/tumor_vs_normal_dummy_clean.csv',
#                             data_dir= os.path.join(args.data_root_dir, 'tumor_vs_normal_resnet_features'),
#                             shuffle = False, 
#                             seed = args.seed, 
#                             print_info = True,
#                             label_dict = {'normal_tissue':0, 'tumor_tissue':1},
#                             patient_strat=False,
#                             ignore=[])

# elif args.task == 'task_2_tumor_subtyping':
#     args.n_classes=3
#     dataset = Generic_MIL_Dataset(csv_path = 'dataset_csv/tumor_subtyping_dummy_clean.csv',
#                             data_dir= os.path.join(args.data_root_dir, 'tumor_subtyping_resnet_features'),
#                             shuffle = False, 
#                             seed = args.seed, 
#                             print_info = True,
#                             label_dict = {'subtype_1':0, 'subtype_2':1, 'subtype_3':2},
#                             patient_strat= False,
#                             ignore=[])

#     if args.model_type in ['clam_sb', 'clam_mb']:
#         assert args.subtyping 
        
# else:
#     raise NotImplementedError
    
if not os.path.isdir(args.results_dir):
    os.mkdir(args.results_dir)

args.results_dir = os.path.join(args.results_dir, str(args.exp_code) + '_s{}'.format(args.seed))
if not os.path.isdir(args.results_dir):
    os.mkdir(args.results_dir)

# if args.split_dir is None:
#     args.split_dir = os.path.join('splits', args.task+'_{}'.format(int(args.label_frac*100)))
# else:
#     args.split_dir = os.path.join('splits', args.split_dir)

# print('split_dir: ', args.split_dir)
# assert os.path.isdir(args.split_dir)

# settings.update({'split_dir': args.split_dir})


with open(args.results_dir + '/experiment_{}.txt'.format(args.exp_code), 'w') as f:
    print(settings, file=f)
f.close()

print("################# Settings ###################")
for key, val in settings.items():
    print("{}:  {}".format(key, val))        

if __name__ == "__main__":
    results = main(args)
    print("finished!")
    print("end script")


