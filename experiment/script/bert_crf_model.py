import torch
import torch.nn as nn
from model import CRF
from transformers import AutoModel, AutoConfig

class BERTCRF(nn.Module):
    """BERT + CRF 序列标注模型。

    处理逻辑:
      1) 传入已经过 tokenizer.encode_plus 得到的 input_ids/attention_mask(按batch拼接)。
      2) 使用 BERT 得到最后一层隐藏向量 (B, L, H)。
      3) 过 dropout + 线性层映射到标签空间 (不含 START/END)。
      4) 训练: 调用 CRF 前向得到平均负对数似然; 推理: CRF.decode 输出标签id路径。

    注意: 这里的 CRF 仍然使用标签数 tag_size (不含 START/END)，并允许 strict_bio 或 enforce_bio。
    """
    def __init__(self, pretrained_model: str, tag_size: int, pad_idx: int, id2tag: dict,
                 dropout: float = 0.1, enforce_bio: bool=False, strict_bio: bool=True,
                 freeze_embeddings: bool=False, freeze_encoder_layers: int=0):
        super().__init__()
        self.config = AutoConfig.from_pretrained(pretrained_model)
        self.bert = AutoModel.from_pretrained(pretrained_model, config=self.config)
        hidden_size = self.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, tag_size)
        self.id2tag = id2tag
        self.crf = CRF(tag_size, pad_idx=pad_idx, enforce_bio=enforce_bio, id2tag=id2tag, strict_bio=strict_bio)

        # 冻结 embedding
        if freeze_embeddings and hasattr(self.bert, 'embeddings'):
            for p in self.bert.embeddings.parameters():
                p.requires_grad = False
        # 冻结前 n 层 encoder layer
        if hasattr(self.bert, 'encoder') and freeze_encoder_layers>0:
            encoder_layers = getattr(self.bert.encoder, 'layer', [])
            for layer in encoder_layers[:freeze_encoder_layers]:
                for p in layer.parameters():
                    p.requires_grad = False

    def forward(self, input_ids, attention_mask=None, tags=None):
        # 文本编码：BERT 将 token 序列编码为上下文表示
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        seq_output = outputs.last_hidden_state  # (B, L, H)
        seq_output = self.dropout(seq_output)
        # 线性映射：将隐藏维 H 映射到标签空间（num_tags），得到每个位置的打分(emissions)
        emissions = self.classifier(seq_output)  # (B, L, num_tags)
        # mask: attention_mask (B,L) -> bool/int
        if tags is not None:
            # 训练：CRF 前向计算负对数似然 (平均)，用于反向传播
            return self.crf(emissions, tags, attention_mask)
        else:
            # 推理：CRF 解码（Viterbi）得到最佳标签路径
            return self.crf.decode(emissions, attention_mask)
