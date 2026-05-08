# Datasets — guia de seleção

Schema MVP: **2 classes** (`helmet`, `vest`). Tudo fora desse escopo é descartado pelo `merge_datasets.py`.

**Princípio**: só usar fontes **estáveis** (GitHub maduro com >100 stars, Roboflow Public benchmark). Datasets de Roboflow Universe upload-by-user são voláteis (deletados/movidos sem aviso) — evitar citar slug fixo.

## Verificação atual (curl HEAD)

URLs abaixo confirmadas no commit deste arquivo. Se algo voltar 404 no futuro, busca alternativa (não invento link).

## Tier 1 — confirmados via curl, pegar todos

### SHWD (Safety Helmet Wearing Dataset) — GitHub
- URL: https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset
- ~7.500 imagens, classes `helmet`, `head`/`person` (VOC format)
- Dataset mais citado em papers de detecção de capacete
- Download:
  ```bash
  git clone https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset \
    ml/datasets/shwd_raw
  python -m ml.prepare.voc_to_yolo \
    --voc-root ml/datasets/shwd_raw \
    --out-root ml/datasets/shwd \
    --images-subdir VOC2028/JPEGImages \
    --annotations-subdir VOC2028/Annotations
  ```

### GDUT-HWD — GitHub
- URL: https://github.com/wujixiu/helmet-detection
- ~3.000 imagens canteiro chinês, capacete por cor (VOC)
- Download:
  ```bash
  git clone https://github.com/wujixiu/helmet-detection ml/datasets/gdut_raw
  python -m ml.prepare.voc_to_yolo \
    --voc-root ml/datasets/gdut_raw \
    --out-root ml/datasets/gdut
  ```

### Pictor-PPE — GitHub
- URL: https://github.com/ciber-lab/pictor-ppe
- ~1.500 imagens canteiro real, formato YOLO direto
- Download:
  ```bash
  git clone https://github.com/ciber-lab/pictor-ppe ml/datasets/pictor_ppe
  ```

### Hard Hat Workers — Roboflow Public
- URL: https://public.roboflow.com/object-detection/hard-hat-workers
- ~7.000 imagens, classes `helmet`, `head`, `person`
- Sem API key necessário
- Download manual: abre URL → "Download Dataset" → format YOLOv8 → descomprime em `ml/datasets/hardhat/`

### Smart_Construction — GitHub (bonus, pequeno)
- URL: https://github.com/PeterH0323/Smart_Construction
- ~500 imagens
- Útil só pra incremento marginal — pode pular sem perda

## Outros caminhos pra achar (estável, sem URL-by-URL)

Se quiser mais dados depois:

```bash
# Roboflow Universe — busca aberta, pega URL ATIVO no momento
xdg-open "https://universe.roboflow.com/search?q=ppe+helmet+vest"
xdg-open "https://universe.roboflow.com/search?q=construction+safety+yolo"

# Kaggle — busca aberta
xdg-open "https://www.kaggle.com/datasets?search=hard+hat+detection"
xdg-open "https://www.kaggle.com/datasets?search=construction+ppe"

# GitHub — filtro por stars
xdg-open "https://github.com/search?q=hard+hat+detection+yolo&type=repositories&s=stars"
```

Critérios pra **adotar** um dataset que achou:
1. ≥ 1.000 imagens
2. helmet E vest separados (não agregado em "ppe")
3. Bbox-anotados (não só classification)
4. License compatível (Public Domain, CC-BY, MIT)
5. Última atualização nos últimos 2 anos OU ≥100 stars (estabilidade)

## NÃO pegar

- "PPE detection" genérico < 500 imagens — fork copiado
- Cor única ("yellow helmet only") — viés
- Selfie/frontal — pose errada vs CCTV
- Qualquer Roboflow Universe slug que **eu** tiver citado mas você verifica e dá 404 — significa foi deletado/renomeado, busca substituto via search

## Pipeline completo (Tier 1)

```bash
source ml/.venv/bin/activate

# Clones diretos (estáveis)
git clone https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset ml/datasets/shwd_raw
git clone https://github.com/wujixiu/helmet-detection ml/datasets/gdut_raw
git clone https://github.com/ciber-lab/pictor-ppe ml/datasets/pictor_ppe

# Hard Hat Workers: download manual no Roboflow Public → ml/datasets/hardhat/

# Conversões VOC → YOLO
python -m ml.prepare.voc_to_yolo \
  --voc-root ml/datasets/shwd_raw \
  --out-root ml/datasets/shwd \
  --images-subdir VOC2028/JPEGImages \
  --annotations-subdir VOC2028/Annotations

python -m ml.prepare.voc_to_yolo \
  --voc-root ml/datasets/gdut_raw \
  --out-root ml/datasets/gdut

# Merge + dedupe
python -m ml.prepare.merge_datasets \
  --sources \
    ml/datasets/shwd \
    ml/datasets/gdut \
    ml/datasets/pictor_ppe \
    ml/datasets/hardhat \
  --output ml/datasets/merged \
  --dedupe --dedupe-threshold 4 \
  --val-ratio 0.15 --test-ratio 0.05
```

Esperado pós-merge: **~14-17k imagens** válidas com helmet+vest.

Suficiente pra mAP@0.5 ≥ 0.85 com yolov8s + 50 epochs.
