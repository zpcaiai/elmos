import torch


def forward(model, values):
    return model(torch.as_tensor(values))
