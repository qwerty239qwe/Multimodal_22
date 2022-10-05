import torch
import os
import torch.utils.tensorboard as tb
from .data import sc_Dataset, load_data
from .model import multimodal_AE, save_model, load_model
from .loss import NBLoss, NCorrLoss
from .utils import corr_score


def train(args):
    """
    Train model.
    """
    # load data
    dataset = sc_Dataset(
            data_path_X = os.path.join(args.data_dir, "cite_train_x.h5ad"),
            data_path_Y = os.path.join(args.data_dir, "cite_train_y.h5ad"),
            time_key = "day",
            celltype_key = "cell_type",
            )
    train_set, val_set = load_data(dataset)
    # init model
    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
    model = multimodal_AE(n_input = dataset.n_feature_X, 
                          n_output= dataset.n_feature_Y,
                          )
    model = model.to(device)
    # optimizer
    if args.optimizer == 'Adam':
        optimizer = torch.optim.Adam(model.parameters(), lr = args.learning_rate, weight_decay = 1e-5)
    elif args.optimizer == 'SGD':
        optimizer = torch.optim.SGD(model.parameters(), lr = args.learning_rate, momentum = 0.9, weight_decay = 5e-4)
    if args.schedule_lr:
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', patience = 5)
    # AE loss
    if args.loss_ae == "nb":
        loss_fn_ae = NBLoss()
    elif args.loss_ae == "gauss":
        loss_fn_ae = torch.nn.GaussianNLLLoss()
    elif args.loss_ae == "ncorr":
        loss_fn_ae = NCorrLoss()
    elif args.loss_ae == "mse":
        loss_fn_ae = torch.nn.MSELoss()
    # logging
    train_logger, valid_logger = None, None
    if args.log_dir is not None:
        train_logger = tb.SummaryWriter(os.path.join(args.log_dir, "train"), flush_secs=1)
        valid_logger = tb.SummaryWriter(os.path.join(args.log_dir, 'valid'), flush_secs=1)
    global_step = 0

    for epoch in range(args.n_epochs):
        model.train()
        corr_sum = 0
        for sample in train_set:
            X_exp, day, celltype, Y_exp = sample
            X_exp, day, celltype, Y_exp =  X_exp.to(device), day.to(device), celltype.to(device), Y_exp.to(device)
            optimizer.zero_grad()
            pred_Y_exp = model(X_exp)
            loss = loss_fn_ae(pred_Y_exp, Y_exp)
            train_logger.add_scalar("loss", loss.item(), global_step)
            corr_sum += corr_score(Y_exp.detach().numpy(), pred_Y_exp.detach().numpy())
            loss.backward()
            optimizer.step()
            global_step += 1
        train_logger.add_scalar("corr", corr_sum/len(train_set), global_step)
        if args.verbose:
            print("epoch: {:03d}, global_step: {:d}, loss: {:.4f}, corr: {:.4f}".format(epoch, global_step, loss.item(), corr_sum/len(train_set)))

        model.eval()
        with torch.no_grad():
            corr_sum = 0
            for sample in val_set:
                X_exp, day, celltype, Y_exp = sample
                X_exp, day, celltype, Y_exp =  X_exp.to(device), day.to(device), celltype.to(device), Y_exp.to(device)
                pred_Y_exp = model(X_exp)
                # loss = loss_fn_ae(pred_Y_exp, Y_exp)
                # valid_logger.add_scalar('loss', loss.item(), global_step)
                corr_sum += corr_score(Y_exp.detach().numpy(), pred_Y_exp.detach().numpy())
            valid_logger.add_scalar("corr", corr_sum/len(val_set), global_step)
            if args.verbose:
                print("epoch: {:03d}, global_step: {:d}, corr: {:.4f}".format(epoch, global_step, corr_sum/len(val_set)))

        if args.schedule_lr:
            train_logger.add_scalar('lr', optimizer.param_groups[0]['lr'], global_step)
            scheduler.step(corr_sum/len(val_set)) # update according to valid set

    if args.save:
        save_model(model)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-D", "--data_dir", type=str, required=True)
    parser.add_argument("--log_dir", type=str, required=True)
    parser.add_argument("-L", "--loss_ae", type=str, default="mse")
    parser.add_argument('-O', '--optimizer', type = str, default = 'Adam')
    parser.add_argument('-lr', '--learning_rate', type = float, default = 0.001)
    parser.add_argument('--schedule_lr', action = 'store_true')
    parser.add_argument("-N", "--n_epochs", type=int, default=100)
    parser.add_argument("-B", "--batch_size", type=int, default=256)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--save", action="store_true")

    args = parser.parse_args()
    print(type(args), args, )
    torch.manual_seed(42) # TODO
    train(args)
    # python -m src.train --data_dir toy_data --log_dir logdir -N 100 -v
