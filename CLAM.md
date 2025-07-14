## installation

```bash
pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple
```

## custom mammography class

`dataset_modules/dataset_generic.py`
```python
class CLAM_MammoDataset(Dataset):
```
exibits all behavior needed to train clam. splits also handeled inside the class so no need to manually create

## train
data_root_dir is path to a yolo format dataset, where empty .txt means normal
```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 python main.py --drop_out 0.25 --early_stopping --lr 2e-4 --k 10 --exp_code task_1_tumor_vs_normal_CLAM_50 --weighted_sample --bag_loss ce --inst_loss svm --task task_1_tumor_vs_normal --model_type clam_sb --log_data --data_root_dir /home/parsa/preprocessing-changes-object/mg-cancer-experimentation/yolo_masks_nocbis_ncrop --embed_dim 512
```

## evaluate (not tested)
```bash
CUDA_VISIBLE_DEVICES=0 python eval.py --k 10 --models_exp_code task_1_tumor_vs_normal_CLAM_50_s1 --save_exp_code task_1_tumor_vs_normal_CLAM_50_s1_cv --task task_1_tumor_vs_normal --model_type clam_sb --results_dir results --data_root_dir /home/parsa/preprocessing-changes-object/mg-cancer-experimentation/yolo_masks_nocbis_ncrop --embed_dim 512
```
