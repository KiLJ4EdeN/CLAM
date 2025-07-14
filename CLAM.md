## installation

```bash
pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple
```

instead we have dicoms here

```
DATA_DIRECTORY/
	├── slide_1.svs
	├── slide_2.svs
	└── ...
```

```bash
python create_patches_fp.py --source DATA_DIRECTORY --save_dir RESULTS_DIRECTORY --patch_size 256 --seg --patch --stitch 
```

TODO: patching must happen in memory since this amount of io will break my hdd
TODO: must work with dicom, must use a segmentation model instead of handmade stuff


```bash
RESULTS_DIRECTORY/
	├── masks
    		├── slide_1.png
    		├── slide_2.png
    		└── ...
	├── patches
    		├── slide_1.h5
    		├── slide_2.h5
    		└── ...
	├── stitches
    		├── slide_1.png
    		├── slide_2.png
    		└── ...
	└── process_list_autogen.csv
```

TODO: changes to dataloader to work in memory

main.py -> our train is also one class
```python
if args.task == 'task_1_tumor_vs_normal':
    args.n_classes=2
    dataset = Generic_MIL_Dataset(csv_path = 'dataset_csv/tumor_vs_normal_dummy_clean.csv',
                            data_dir= os.path.join(args.data_root_dir, 'tumor_vs_normal_feat_resnet'),
                            shuffle = False, 
                            seed = args.seed, 
                            print_info = True,
                            label_dict = {'normal_tissue':0, 'tumor_tissue':1},
                            label_col = 'label',
                            ignore=[])
```

python create_splits_seq.py --task task_1_tumor_vs_normal --seed 1 --k 10 -> splits in memory also

```bash
CUDA_VISIBLE_DEVICES=0 python main.py --drop_out 0.25 --early_stopping --lr 2e-4 --k 10 --exp_code task_1_tumor_vs_normal_CLAM_50 --weighted_sample --bag_loss ce --inst_loss svm --task task_1_tumor_vs_normal --model_type clam_sb --log_data --data_root_dir DATA_ROOT_DIR --embed_dim 1024
```
```bash
CUDA_VISIBLE_DEVICES=0 python main.py --drop_out 0.25 --early_stopping --lr 2e-4 --k 10 --exp_code task_1_tumor_vs_normal_CLAM_50 --bag_loss ce --inst_loss svm --task task_1_tumor_vs_normal --model_type clam_sb --log_data --data_root_dir DATA_ROOT_DIR --embed_dim 2048
```

train with adapted loaders and seg

```bash
CUDA_VISIBLE_DEVICES=0 python eval.py --k 10 --models_exp_code task_1_tumor_vs_normal_CLAM_50_s1 --save_exp_code task_1_tumor_vs_normal_CLAM_50_s1_cv --task task_1_tumor_vs_normal --model_type clam_sb --results_dir results --data_root_dir DATA_ROOT_DIR --embed_dim 1024
```
