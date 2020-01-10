#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Sep 18 16:14:19 2019

In this script we are looking at the transfer learning of a VGG with some 
statistics imposed on the features maps of the layers

@author: gonthier
"""


from preprocess_crop import load_and_crop_img,load_and_crop_img_forImageGenerator

from trouver_classes_parmi_K import TrainClassif
import numpy as np
import matplotlib
import os.path
from Study_Var_FeaturesMaps import get_dict_stats,numeral_layers_index,numeral_layers_index_bitsVersion
from Stats_Fcts import vgg_cut,vgg_InNorm_adaptative,vgg_InNorm,vgg_BaseNorm,\
    load_resize_and_process_img,VGG_baseline_model,vgg_AdaIn,ResNet_baseline_model,\
    MLP_model,Perceptron_model,vgg_adaDBN,ResNet_AdaIn,ResNet_BNRefinements_Feat_extractor,\
    ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction,ResNet_cut,vgg_suffleInStats,\
    get_ResNet_ROWD_meanX_meanX2_features,get_BaseNorm_meanX_meanX2_features,\
    get_VGGmodel_meanX_meanX2_features,add_head_and_trainable,extract_Norm_stats_of_ResNet,\
    vgg_FRN,set_momentum_BN
from IMDB import get_database
import pickle
import pathlib
from Classifier_On_Features import TrainClassifierOnAllClass,PredictOnTestSet
from sklearn.metrics import average_precision_score,recall_score,make_scorer,\
    precision_score,label_ranking_average_precision_score,classification_report
from sklearn.metrics import matthews_corrcoef,f1_score
from sklearn.preprocessing import StandardScaler
from Custom_Metrics import ranking_precision_score
from LatexOuput import arrayToLatex
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.python.keras import backend as K
from numba import cuda
import matplotlib.pyplot as plt
import matplotlib.cm as mplcm
import matplotlib.colors as colors
from matplotlib.backends.backend_pdf import PdfPages
import gc 
import tempfile
from tensorflow.python.keras.callbacks import ModelCheckpoint
from tensorflow.python.keras.models import load_model
from keras_resnet_utils import getBNlayersResNet50,getResNetLayersNumeral,getResNetLayersNumeral_bitsVersion,\
    fit_generator_ForRefineParameters,fit_generator_ForRefineParameters_v2
import keras_preprocessing as kp

from functools import partial
from sklearn.metrics import average_precision_score,make_scorer
from sklearn.model_selection import GridSearchCV


def compute_ref_stats(dico,style_layers,type_ref='mean',imageUsed='all',whatToload = 'varmean',applySqrtOnVar=False):
    """
    This function compute a reference statistics on the statistics of the whole dataset
    """
    vgg_stats_values = []
    for l,layer in enumerate(style_layers):
        stats = dico[layer]
        if whatToload == 'varmean':
            if imageUsed=='all':
                if type_ref=='mean':
                    mean_stats = np.mean(stats,axis=0) # First colunm = variance, second = mean
                    mean_of_means = mean_stats[1,:]
                    mean_of_vars = mean_stats[0,:]
                    if applySqrtOnVar:
                        mean_of_vars = np.sqrt(mean_of_vars) # STD
                    vgg_stats_values += [[mean_of_means,mean_of_vars]]
                    # To return vgg_mean_vars_values
    return(vgg_stats_values)

def get_dict_stats_BaseNormCoherent(target_dataset,source_dataset,target_number_im_considered,\
                                    style_layers,\
                                    list_mean_and_std_source,whatToload,saveformat='h5',\
                                    getBeforeReLU=False,target_set='trainval',applySqrtOnVar=True,\
                                    Net='VGG',cropCenter=False,BV=True,cumulativeWay=False,verbose=False,\
                                    useFloat32=False,computeGlobalVariance=False):
    """
    The goal of this function is to compute a version of the statistics of the 
    features of the VGG or ResNet50
    """
    
    if not(cumulativeWay):
        # We will compute and save the mean and covariance of all the images 
        # En then compute the variances on it
        dict_stats_coherent = {} 
        for i_layer,layer_name in enumerate(style_layers):
            if verbose: print(i_layer,layer_name)
            if i_layer==0:
                style_layers_firstLayer = [layer_name]
                dict_stats_target0 = get_dict_stats(target_dataset,target_number_im_considered,\
                                                    style_layers_firstLayer,\
                                                    whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,\
                                                    set=target_set,Net=Net,cropCenter=cropCenter,BV=BV)
                dict_stats_coherent[layer_name] = dict_stats_target0[layer_name]
                list_mean_and_std_target_i_m1 = compute_ref_stats(dict_stats_target0,\
                                                style_layers_firstLayer,type_ref='mean',\
                                                imageUsed='all',whatToload=whatToload,\
                                                applySqrtOnVar=applySqrtOnVar)
                current_list_mean_and_std_target = list_mean_and_std_target_i_m1
            else:
                style_layers_imposed = style_layers[0:i_layer]
                style_layers_exported = [style_layers[i_layer]]
                
                if 'ROWD' in Net or list_mean_and_std_source is None:
                    list_mean_and_std_source_i = None
                else:
                    list_mean_and_std_source_i = list_mean_and_std_source[0:i_layer]
                
                dict_stats_target_i = get_dict_stats(target_dataset,target_number_im_considered,\
                                                     style_layers=style_layers_exported,whatToload=whatToload,\
                                                     saveformat='h5',getBeforeReLU=getBeforeReLU,\
                                                     set=target_set,Net=Net,\
                                                     style_layers_imposed=style_layers_imposed,\
                                                     list_mean_and_std_source=list_mean_and_std_source_i,\
                                                     list_mean_and_std_target=current_list_mean_and_std_target,\
                                                     cropCenter=cropCenter,BV=BV)
                dict_stats_coherent[layer_name] = dict_stats_target_i[layer_name]
                # Compute the next statistics 
                list_mean_and_std_target_i = compute_ref_stats(dict_stats_target_i,\
                                                style_layers_exported,type_ref='mean',\
                                                imageUsed='all',whatToload=whatToload,\
                                                applySqrtOnVar=applySqrtOnVar)
                current_list_mean_and_std_target += [list_mean_and_std_target_i[-1]]
    else:
        # In this case we will only return the list of the mean and std on the target set
        if verbose: print('We will use a cumulative way to compute the statistics.')
        current_list_mean_and_std_target = []
        if 'VGG' in Net:
            if BV:
                str_layers = numeral_layers_index(style_layers)
            else:
                str_layers = numeral_layers_index_bitsVersion(style_layers)
        elif 'ResNet50' in Net:
            if BV:
                str_layers = getResNetLayersNumeral_bitsVersion(style_layers,num_layers=50)
            else:
                str_layers = getResNetLayersNumeral(style_layers,num_layers=50)
        else:
            raise(NotImplementedError)
        if 'ROWD' in Net: 
            # In this case we don t take into account the source_dataset only the target one
            filename = Net+'_OnlyCoherentStats_MeanStd_'+str_layers
        else:
            filename = Net+'_OnlyCoherentStats_'+source_dataset + '_' + str(target_number_im_considered) +\
                '_MeanStd'+'_'+str_layers
        if cropCenter:
            filename += '_cropCenter'
        if computeGlobalVariance:
            filename +='_computeGlobalVariance'

        output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp')
        if os.path.isdir(output_path):
            output_path_full = os.path.join(output_path,'Covdata','data')
        else:
            output_path_full = os.path.join('data','Covdata')
        pathlib.Path(output_path_full).mkdir(parents=True, exist_ok=True)  
        
        filename += '_TD_'+target_dataset
        if not(target_set=='' or target_set is None):
            filename += '_'+ target_set
        if 'VGG' in Net and getBeforeReLU:
            filename += '_BeforeReLU'
        filename += '.pkl'
        filename_path= os.path.join(output_path_full,filename)
        if verbose: print('The filename is :',filename_path)
        if not os.path.isfile(filename_path):
            dict_stats_coherent = {} 
            for i_layer,layer_name in enumerate(style_layers):
                if verbose: print(i_layer,layer_name)
                if i_layer==0:
                    style_layers_firstLayer = [layer_name]
                    mean_and_std_layer = compute_mean_std_onDataset(target_dataset,target_number_im_considered,style_layers_firstLayer,\
                                                                    set=target_set,getBeforeReLU=getBeforeReLU,\
                                                                    Net=Net,style_layers_imposed=[],\
                                                                    list_mean_and_std_source=None,list_mean_and_std_target=None,\
                                                                    cropCenter=cropCenter,useFloat32=useFloat32,
                                                                    computeGlobalVariance=computeGlobalVariance)
                    dict_stats_coherent[layer_name] = mean_and_std_layer
                    current_list_mean_and_std_target = [mean_and_std_layer]
                else:
                    style_layers_imposed = style_layers[0:i_layer]
                    style_layers_exported = [style_layers[i_layer]]
                    
                    if 'ROWD' in Net or list_mean_and_std_source is None:
                        list_mean_and_std_source_i = None
                    else:
                        list_mean_and_std_source_i = list_mean_and_std_source[0:i_layer]
                    style_layers_firstLayer = [layer_name]
                    mean_and_std_layer = compute_mean_std_onDataset(target_dataset,target_number_im_considered,style_layers_firstLayer,\
                                                                    set=target_set,getBeforeReLU=getBeforeReLU,\
                                                                    Net=Net,style_layers_imposed=style_layers_imposed,\
                                                                    list_mean_and_std_source=list_mean_and_std_source_i,\
                                                                    list_mean_and_std_target=current_list_mean_and_std_target,\
                                                                    cropCenter=cropCenter,useFloat32=useFloat32,
                                                                    computeGlobalVariance=computeGlobalVariance)
                    dict_stats_coherent[layer_name] = mean_and_std_layer
                    current_list_mean_and_std_target += [mean_and_std_layer]
            # Need to save the dict_stats_coherent 
            with open(filename_path, 'wb') as handle:
                pickle.dump(dict_stats_coherent, handle, protocol=pickle.HIGHEST_PROTOCOL)
        else:
            with open(filename_path, 'rb') as handle:
                dict_stats_coherent = pickle.load(handle)
            for i_layer,layer_name in enumerate(style_layers):
                mean_and_std_layer =  dict_stats_coherent[layer_name]
                current_list_mean_and_std_target += [mean_and_std_layer]
    
    return(dict_stats_coherent,current_list_mean_and_std_target)

def compute_mean_std_onDataset(dataset,number_im_considered,style_layers,\
                   set='',getBeforeReLU=False,\
                   Net='VGG',style_layers_imposed=[],\
                   list_mean_and_std_source=[],list_mean_and_std_target=[],\
                   cropCenter=False,useFloat32=True,computeGlobalVariance=False):
    """
    this function will directly compute mean and std of the features maps on the source_dataset
    in an efficient way without saving covariance matrices for the style_layers
    @param : computeGlobalVariance : if False : compute the mean of the variance of the different images
        if True : compute the global variance on the whole image and spatial position
    """
    # Les differents reseaux retournr la moyenne spatiale des features et la 
    # moyenne spatiale des carrées des features
    graph1 = tf.Graph()
    with graph1.as_default():
        session1 = tf.Session()
        with session1.as_default():
    
            if Net=='VGG':
                net_get_SpatialMean_SpatialMeanOfSquare =  get_VGGmodel_meanX_meanX2_features(style_layers,getBeforeReLU=getBeforeReLU)
            elif Net=='VGGBaseNorm' or Net=='VGGBaseNormCoherent':
                style_layers_exported = style_layers
                net_get_SpatialMean_SpatialMeanOfSquare = get_BaseNorm_meanX_meanX2_features(style_layers_exported,\
                                style_layers_imposed,list_mean_and_std_source,list_mean_and_std_target,\
                                getBeforeReLU=getBeforeReLU)
            elif 'ResNet50_ROWD_CUMUL' in Net: # Base coherent here also but only update the batch normalisation
                style_layers_exported = style_layers
                net_get_SpatialMean_SpatialMeanOfSquare = get_ResNet_ROWD_meanX_meanX2_features(style_layers_exported,style_layers_imposed,\
                                            list_mean_and_std_target,transformOnFinalLayer=None,
                                            res_num_layers=50,weights='imagenet')
            else:
                print(Net,'is inknown')
                raise(NotImplementedError)
            # Load info about dataset
            item_name,path_to_img,default_path_imdb,classes,ext,num_classes,str_val,df_label,\
            path_data,Not_on_NicolasPC = get_database(dataset)
            
            if set=='train':
                df = df_label[df_label['set']=='train']
            elif set=='test':
                df = df_label[df_label['set']=='test']
            elif set==str_val or set=='val' or set=='validation':
                df = df_label[df_label['set']==str_val]
            elif set=='trainval':
                df1 = df_label[df_label['set']=='train']
                df2 = df_label[df_label['set']==str_val]
                df =df1.append(df2)
            x_col = item_name
            df[x_col] = df[x_col].apply(lambda x : x + '.jpg')
            
            
            if cropCenter:
                interpolation='lanczos:center'
                old_loading_img_fct = kp.image.iterator.load_img
                kp.image.iterator.load_img = partial(load_and_crop_img_forImageGenerator,Net=Net)
            else:
                interpolation='nearest'
            if 'VGG' in Net:
                preprocessing_function = tf.keras.applications.vgg19.preprocess_input
                target_size = (224,224)
            elif 'ResNet50' in Net:
                preprocessing_function = tf.keras.applications.resnet50.preprocess_input
                target_size = (224,224)
            else:
                print(Net,'is unknwon')
                raise(NotImplementedError)
                    
            use_multiprocessing = True
            workers = 8
            
            datagen= tf.keras.preprocessing.image.ImageDataGenerator(preprocessing_function=preprocessing_function)
            
            test_generator=datagen.flow_from_dataframe(dataframe=df, directory=path_to_img,\
                                                        x_col=x_col,\
                                                        class_mode=None,shuffle=False,\
                                                        target_size=target_size, batch_size=32,\
                                                        use_multiprocessing=use_multiprocessing,workers=workers,interpolation=interpolation)
            predictions = net_get_SpatialMean_SpatialMeanOfSquare.predict_generator(test_generator)
            meanX,meanX2 = predictions
        #    if dtype=='float64':
        #        meanX.astype('float64')
        #        meanX2.astype('float64')
        #    print(meanX.shape,meanX2.shape)
        #    print(meanX)
        #    print(meanX2)
            
            
            if computeGlobalVariance:
                meanX2.astype('float64')
                meanX.astype('float64')
                expectation_meanX = np.mean(meanX,axis=0)
                mean_global_X2 = np.mean(meanX2,axis=0)
                
                varX = mean_global_X2 - np.power(expectation_meanX,2)
                
            #    varX_beforeClip = varX
            #    varX = np.where(varX<0.0 and varX>=-10**(-5), 0.0, varX)
                varX = varX.clip(min=0.0)
                try:
                    assert(varX>=0).all()
                except AssertionError as e:
                    print('varX negative values :',varX[np.where(varX<0.0)])
                    print('varX negative index :',np.where(varX<0.0))
                    raise(e)
                expectation_stdX = np.sqrt(varX)
                expectation_stdX.astype('float32')
                expectation_meanX.astype('float32')
            else:
                expectation_meanX = np.mean(meanX,axis=0)
                varX = meanX2 - np.power(meanX,2)
            #    varX_beforeClip = varX
            #    varX = np.where(varX<0.0 and varX>=-10**(-5), 0.0, varX)
                varX = varX.clip(min=0.0)
        #    print(varX)
                try:
                    assert(varX>=0).all()
                except AssertionError as e:
                    print('varX negative values :',varX[np.where(varX<0.0)])
                    print('varX negative index :',np.where(varX<0.0))
                    raise(e)
                expectation_stdX = np.mean(np.sqrt(varX),axis=0)
        #    if dtype=='float64':
        #        expectation_meanX.astype('float32')
        #        expectation_stdX.astype('float32')
            del net_get_SpatialMean_SpatialMeanOfSquare
        
        if cropCenter:
            kp.image.iterator.load_img = old_loading_img_fct
            
    return(expectation_meanX,expectation_stdX)

def learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='block5_pool',\
                   constrNet='VGG',kind_method='FT',\
                   style_layers = ['block1_conv1',
                                    'block2_conv1',
                                    'block3_conv1', 
                                    'block4_conv1', 
                                    'block5_conv1'
                                   ],normalisation=False,gridSearch=True,ReDo=False,\
                                   transformOnFinalLayer='',number_im_considered = 10000,\
                                   set='',getBeforeReLU=True,forLatex=False,epochs=20,\
                                   pretrainingModif=True,weights='imagenet',opt_option=[0.01],\
                                   optimizer='SGD',freezingType='FromTop',verbose=False,\
                                   plotConv=False,batch_size=32,regulOnNewLayer=None,\
                                   regulOnNewLayerParam=[],return_best_model=False,\
                                   onlyReturnResult=False,dbn_affine=True,m_per_group=16,
                                   momentum=0.9,batch_size_RF=16,epochs_RF=20,cropCenter=True,\
                                   BV=True,dropout=None,nesterov=False,SGDmomentum=0.0,decay=0.0,\
                                   kind_of_shuffling='shuffle',useFloat32=True,\
                                   computeGlobalVariance=True,returnStatistics=False,returnFeatures=False,\
                                   NoValidationSetUsed=False,RandomValdiationSet=False):
    """
    @param : the target_dataset used to train classifier and evaluation
    @param : source_dataset : used to compute statistics we will imposed later
    @param : final_clf : the final classifier can be
        - linear SVM 'LinearSVC' or two layers NN 'MLP2' or MLP1 for perceptron
    @param : features : which features we will use
        - fc2, fc1, flatten block5_pool (need a transformation) for VGG
    @param : constrNet the constrained net used :
        VGG
        VGGInNorm
        VGGInNormAdapt : seulement sur les features qui répondent trop fort
        VGGBaseNorm
        VGGBaseNormCoherent
        ResNet50
        ResNet50_ROWD
        ResNet50_ROWD_CUMUL
        ResNet50_BNRF
        VGGAdaIn
        VGGBaseNormCoherentAdaIn
        VGGFRN
        VGGAdaDBN
        VGGsuffleInStats
        ResNet50AdaIn
        ResNet50_ROWD_CUMUL_AdaIn : fine tune only the batch normalisation refined

        TODO : VGGGram that modify the gram matrices
    @param : kind_method the type of methods we will use : TL or FT
    @param : if we use a set to compute the statistics
    @param : getBeforeReLU=False if True we will impose the statistics before the activation ReLU fct
        !!! Only for VGG model 
    @param : forLatex : only plot performance score to print them in latex
    @param : epochs number of epochs for the finetuning (FT case)
    @param : pretrainingModif : we modify the pretrained net for the case FT + VGG 
        it can be a boolean True of False or a 
    @param : opt_option : learning rate different for the SGD
    @param : freezingType : the way we unfreeze the pretained network : 'FromBottom','FromTop','Alter'
    @param : ReDo : we erase the output performance file
    @param : plotConv : plot the loss function in train and val
    @param : regulOnNewLayer : None l1 l2 or l1_l2
    @param : regulOnNewLayerParam the weight on the regularizer
    @param : return_best_model if True we will load and return the best model
    @param : onlyReturnResult : only return the results if True and nothing computed will return None
    @param : dbn_affine : use of Affine decorrelated BN in  VGGAdaDBN model
    @param : m_per_group : number of group for the VGGAdaDBN model (with decorrelated BN)
    @param : momentum : momentum for the refinement of the batch statistics
    @param : batch_size_RF : batch size for the refinement of the batch statistics
    @param : epochs_RF : number of epochs for the refinement of the batch statistics
    @param : cropCenter if True we only consider the central crop of the image as in Crowley 2016
    @param : BV : if true use the compress value for the layer index
    @param : dropout : if None no dropout otherwise on the new layer
    @param : nesterov : nesterov approximation for MLP
    @param : SGDmomentum : SGD momentum in the gradient descent
    @param : decay : learning rate decay for MLP model
    @param : kind_of_shuffling=='shuffle' or 'roll'  for VGGshuffleInStats
    @param : useFloat32 is the use of float32 for cumulated spatial mean of features and squared features
    @param : computeGlobalVariance if True compute the global variance in the case of ResNet50_ROWD_CUMUL 
    @param : returnStatistics : if True in the case of ResNet, ROWD and BNRF, we return the normalisation statistics computer by the refinement step
    @param : returnFeatures : if True in the case of ResNet, ROWD and BNRF, we return the features precomputed along with the labels
    @param : NoValidationSetUsed : means that we don't use a validation set for selecting the best model or other stuff, we will use the whole trainval dataset for training
    @param : RandomValdiationSet : means that we don't use a provide validation set for selecting the best model but a fraction of the trainval set
    """
#    tf.enable_eager_execution()
    # for ResNet you need to use different layer name such as  ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']
    
    #tf.compat.v1.enable_eager_execution()
    
    if constrNet=='ResNet50_BNRF' and kind_method=='FT':
        style_layers = getBNlayersResNet50()
        print('Need to be all BN layers of ResNet')
        
    if final_clf=='LinearSVC' and kind_method=='FT':
        print('You can not have LinearSVC and finetuning ie FT option at the same time')
        print('With FT option you have to use MLP final classifier')
        raise(NotImplementedError)
        
        
    assert(not(returnStatistics and returnFeatures)) # Need to choose between both
    assert(freezingType in ['FromBottom','FromTop','Alter'])
    
    output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',target_dataset)
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True) 
    if kind_method=='FT':
        model_output_path = os.path.join(output_path,'model')
        pathlib.Path(model_output_path).mkdir(parents=True, exist_ok=True) 
    
    if kind_method=='TL':
        if not (transformOnFinalLayer is None or transformOnFinalLayer=='') and features in ['fc2','fc1','flatten','avg_pool']:
            print('Incompatible feature layer and transformation applied to this layer')
            raise(NotImplementedError)
    
    if 'VGG' in  constrNet: 
        if BV:
            num_layers = numeral_layers_index_bitsVersion(style_layers)
        else:
            num_layers = numeral_layers_index(style_layers)
    elif 'ResNet' in constrNet:
        if BV: 
            num_layers = getResNetLayersNumeral_bitsVersion(style_layers)
        else: 
            num_layers = getResNetLayersNumeral(style_layers)
    # Compute statistics on the source_dataset
    if source_dataset is None:
        constrNet='VGG'
        
    # Load info about dataset
    item_name,path_to_img,default_path_imdb,classes,ext,num_classes,str_val,df_label,\
    path_data,Not_on_NicolasPC = get_database(target_dataset)
        
    name_base = constrNet + '_'  +target_dataset +'_'
    if not(constrNet=='VGG') and not(constrNet=='ResNet50'):
        if kind_method=='TL' and constrNet in ['VGGInNorm','VGGInNormAdapt','VGGBaseNorm','VGGBaseNormCoherent']:
            name_base += source_dataset +str(number_im_considered)
        name_base +=  '_' + num_layers
    if kind_method=='FT' and (weights is None):
        name_base += '_RandInit' # Random initialisation 
        
    if len(opt_option)>1 and not(optimizer=='SGD'):
        print('The multiple learning rate for optimizer is only implemented for SGD for the moments')
        raise(NotImplementedError)        
        
    if kind_method=='FT':
        if not(optimizer=='adam'):
            name_base += '_'+optimizer
        if len(opt_option)==2:
            multiply_lrp, lr = opt_option
            name_base += '_lrp'+str(multiply_lrp)+'_lr'+str(lr)
        if len(opt_option)==1:
            lr = opt_option[0]
            name_base += '_lr'+str(lr)
        # Default value used
        if constrNet=='VGGAdaDBN':
            name_base += '_MPG'+str(m_per_group)
            if dbn_affine:
                name_base += '_Affine'
                
    if constrNet=='ResNet50_BNRF': # BN Refinement
        name_base += '_m'+str(momentum)+'_bsRF'+str(batch_size_RF)+'_ep'+str(epochs_RF)
        
    if constrNet=='ResNet50_ROWD_CUMUL_AdaIn' or constrNet=='ResNet50_BNRF_AdaIn':
        name_base += '_Retrained'+str(num_layers)
            
    if not(set=='' or set is None):
        name_base += '_'+set
    if constrNet=='VGG' or constrNet=='ResNet50':
        getBeforeReLU  = False
    if constrNet in ['VGG','ResNet50'] and kind_method=='FT':
        if type(pretrainingModif)==bool:
            if pretrainingModif==False:
                name_base +=  '_wholePretrainedNetFreeze'
        else:
            if not(freezingType=='FromTop'):
                name_base += '_'+freezingType
            name_base += '_unfreeze'+str(pretrainingModif)
     
    if 'VGG' in constrNet:
        if getBeforeReLU:
            name_base += '_BeforeReLU'
#    if not(kind_method=='FT' and constrNet=='VGGAdaIn'):
#        name_base +=  features 
    if 'VGG' in constrNet: # VGG kind family
        if features in  ['fc2','fc1','flatten']:
            name_base += '_' + features
        else:
            if not(features=='block5_pool'):
                name_base += '_' + features
            if not((transformOnFinalLayer is None) or (transformOnFinalLayer=='')):
               name_base += '_'+ transformOnFinalLayer
    elif 'ResNet' in constrNet: # ResNet kind family
        if features in ['avg_pool']: # A remplir
            name_base += '_' + features
        else:
            if not(features=='activation_48'): # TODO ici
                name_base += '_' + features
            if not((transformOnFinalLayer is None) or (transformOnFinalLayer=='')):
               name_base += '_'+ transformOnFinalLayer
   
    if constrNet=='VGGsuffleInStats':
        if not(kind_of_shuffling=='shuffle'):
            name_base += '_'+ kind_of_shuffling
   
    if constrNet=='ResNet50_ROWD_CUMUL' and useFloat32:
        name_base += '_useFloat32'
    
    if cropCenter:   
        name_base += '_CropCenter'  
        
    if constrNet=='ResNet50_ROWD_CUMUL' and computeGlobalVariance:
        name_base += '_computeGlobalVariance'
        
    name_base += '_' + kind_method   
    
    # features can be 'flatten' with will output a 25088 dimension vectors = 7*7*512 features
    
    curr_session = tf.get_default_session()
    # close current session
    if curr_session is not None:
        curr_session.close()
    # reset graph
    K.clear_session()
    # create new session
    s = tf.InteractiveSession()
    K.set_session(s)
    
    if kind_method=='TL': # Transfert Learning
        final_layer = features
        name_pkl_im = target_dataset +'.pkl'
        name_pkl_values  = name_base+ '_Features.pkl'
        name_pkl_im = os.path.join(output_path,name_pkl_im)
        name_pkl_values = os.path.join(output_path,name_pkl_values)

        if  not(onlyReturnResult) or returnStatistics:
            if not os.path.isfile(name_pkl_values) or returnStatistics:
                if not(forLatex):
                    print('== We will compute or load the reference statistics and / or the extraction features network ==')
                    print('The Saving file is',name_pkl_values)
                features_net = None
                im_net = []
                # Load Network 
                if constrNet=='VGG':
                    network_features_extraction = vgg_cut(final_layer,\
                                                          transformOnFinalLayer=transformOnFinalLayer,\
                                                          weights='imagenet')
                elif constrNet=='VGGInNorm' or constrNet=='VGGInNormAdapt':
                    whatToload = 'varmean'
                    dict_stats = get_dict_stats(source_dataset,number_im_considered,style_layers,\
                           whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,set=set,Net='VGG',\
                           cropCenter=cropCenter,BV=BV)
                    # Compute the reference statistics
                    vgg_mean_stds_values = compute_ref_stats(dict_stats,style_layers,type_ref='mean',\
                                                         imageUsed='all',whatToload =whatToload,
                                                         applySqrtOnVar=True)
                    if constrNet=='VGGInNormAdapt':
                        network_features_extraction = vgg_InNorm_adaptative(style_layers,
                                                                           vgg_mean_stds_values,
                                                                           final_layer=final_layer,
                                                                           transformOnFinalLayer=transformOnFinalLayer,
                                                                           HomeMadeBatchNorm=True,getBeforeReLU=getBeforeReLU)
                    elif constrNet=='VGGInNorm':
                        network_features_extraction = vgg_InNorm(style_layers,
                                                                vgg_mean_stds_values,
                                                                final_layer=final_layer,
                                                                transformOnFinalLayer=transformOnFinalLayer,
                                                                HomeMadeBatchNorm=True,getBeforeReLU=getBeforeReLU)
                elif constrNet=='VGGBaseNorm':
                    whatToload = 'varmean'
                    dict_stats_source = get_dict_stats(source_dataset,number_im_considered,style_layers,\
                           whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,set=set,Net='VGG',\
                           cropCenter=cropCenter,BV=BV)
                    # Compute the reference statistics
                    list_mean_and_std_source = compute_ref_stats(dict_stats_source,style_layers,type_ref='mean',\
                                                         imageUsed='all',whatToload =whatToload,
                                                         applySqrtOnVar=True)
                    target_number_im_considered = None
                    target_set = 'trainval' # Todo ici
                    dict_stats_target = get_dict_stats(target_dataset,target_number_im_considered,style_layers,\
                           whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,set=target_set,\
                           cropCenter=cropCenter,BV=BV)
                    # Compute the reference statistics
                    list_mean_and_std_target = compute_ref_stats(dict_stats_target,style_layers,type_ref='mean',\
                                                         imageUsed='all',whatToload =whatToload,
                                                         applySqrtOnVar=True)
    #                
    #                
                    network_features_extraction = vgg_BaseNorm(style_layers,list_mean_and_std_source,
                        list_mean_and_std_target,final_layer=final_layer,transformOnFinalLayer=transformOnFinalLayer,
                        getBeforeReLU=getBeforeReLU)
                    
                elif constrNet=='VGGBaseNormCoherent':
                    # A more coherent way to compute the VGGBaseNormalisation
                    # We will pass the dataset several time through the net modify bit after bit to 
                    # get the coherent mean and std of the target domain
                    whatToload = 'varmean'
                    dict_stats_source = get_dict_stats(source_dataset,number_im_considered,style_layers,\
                           whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,set=set,Net='VGG',\
                           cropCenter=cropCenter,BV=BV)
                    # Compute the reference statistics
                    list_mean_and_std_source = compute_ref_stats(dict_stats_source,style_layers,type_ref='mean',\
                                                         imageUsed='all',whatToload =whatToload,
                                                         applySqrtOnVar=True)
                    target_number_im_considered = None
                    target_set = 'trainval'
                    dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(target_dataset,source_dataset,target_number_im_considered,\
                           style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                           getBeforeReLU=getBeforeReLU,target_set=target_set,\
                           applySqrtOnVar=True,cropCenter=cropCenter,BV=BV,verbose=verbose) # It also computes the reference statistics (mean,var)
                    
                    network_features_extraction = vgg_BaseNorm(style_layers,list_mean_and_std_source,
                        list_mean_and_std_target,final_layer=final_layer,transformOnFinalLayer=transformOnFinalLayer,
                        getBeforeReLU=getBeforeReLU)
                
                elif constrNet=='ResNet50':
                    # in the case of ResNet50 : final_alyer = features = 'activation_48'
                    network_features_extraction = ResNet_cut(final_layer=features,\
                                     transformOnFinalLayer =transformOnFinalLayer,\
                             verbose=verbose,weights=weights,res_num_layers=50)
                    
                    if returnStatistics:
                        return(network_features_extraction)
                        
                elif constrNet=='ResNet50_ROWD':
                    # Refinement the batch normalisation : normalisation statistics
                    # Once on the Whole train val Dataset on new dataset
                    list_mean_and_std_source = None
                    target_number_im_considered = None
                    whatToload = 'varmean'
                    target_set = 'trainval'
                    dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(
                            target_dataset,source_dataset,target_number_im_considered,\
                            style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                            getBeforeReLU=getBeforeReLU,target_set=target_set,\
                            applySqrtOnVar=True,Net=constrNet,cropCenter=cropCenter,\
                            BV=BV,verbose=verbose) # It also computes the reference statistics (mean,var)
                    
                    if returnStatistics:
                        return(dict_stats_target,list_mean_and_std_target)
                        
                    network_features_extraction = ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction(
                                   style_layers,list_mean_and_std_target=list_mean_and_std_target,\
                                   final_layer=features,\
                                   transformOnFinalLayer=transformOnFinalLayer,res_num_layers=50,\
                                   weights=weights)
                    
                elif constrNet=='ResNet50_ROWD_CUMUL':
                    # Refinement the batch normalisation : normalisation statistics
                    # Once on the Whole train val Dataset on new dataset
                    # In a cumulative way to be more efficient
                    # Il faudrait peut etre mieux gerer les cas ou la variances est négatives
                    list_mean_and_std_source = None
                    target_number_im_considered = None
                    whatToload = 'varmean'
                    target_set = 'trainval'
                    dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(
                            target_dataset,source_dataset,target_number_im_considered,\
                            style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                            getBeforeReLU=getBeforeReLU,target_set=target_set,\
                            applySqrtOnVar=True,Net=constrNet,cropCenter=cropCenter,\
                            BV=BV,cumulativeWay=True,verbose=verbose,useFloat32=useFloat32,\
                            computeGlobalVariance=computeGlobalVariance) # It also computes the reference statistics (mean,var)
                    
                    if returnStatistics:
                        return(dict_stats_target,list_mean_and_std_target)

                    network_features_extraction = ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction(
                                   style_layers,list_mean_and_std_target=list_mean_and_std_target,\
                                   final_layer=features,\
                                   transformOnFinalLayer=transformOnFinalLayer,res_num_layers=50,\
                                   weights=weights)
                    
                elif constrNet=='ResNet50_BNRF':
                    res_num_layers = 50
                    network_features_extraction= get_ResNet_BNRefin(df=df_label,\
                                    x_col=item_name,path_im=path_to_img,\
                                    str_val=str_val,num_of_classes=len(classes),Net=constrNet,\
                                    weights=weights,res_num_layers=res_num_layers,\
                                    transformOnFinalLayer=transformOnFinalLayer,\
                                    kind_method=kind_method,\
                                    batch_size=batch_size_RF,momentum=momentum,\
                                    num_epochs_BN=epochs_RF,output_path=output_path,\
                                    cropCenter=cropCenter)
                    if returnStatistics:
                        return(network_features_extraction)

                else:
                    print(constrNet,'is unknown')
                    raise(NotImplementedError)
                    
                if not(forLatex):
                    if verbose: print('== We will compute the bottleneck features ==')
                # Compute bottleneck features on the target dataset
                for i,name_img in  enumerate(df_label[item_name]):
                    im_path =  os.path.join(path_to_img,name_img+'.jpg')
                    if cropCenter:
                        image = load_and_crop_img(path=im_path,Net=constrNet,target_size=224,
                                            crop_size=224,interpolation='lanczos:center')
                          # It's also process the images
                          # For VGG or ResNet size == 224
                    else:
                        image = load_resize_and_process_img(im_path,Net=constrNet)
                    features_im = network_features_extraction.predict(image)
                    #print(i,name_img,features_im.shape,features_im[0,0:10])
                    if features_net is not None:
                        features_net = np.vstack((features_net,np.array(features_im)))
                        im_net += [name_img]
                    else:
                        features_net =np.array(features_im)
                        im_net = [name_img]
                with open(name_pkl_values, 'wb') as pkl:
                    pickle.dump(features_net,pkl)
                
                with open(name_pkl_im, 'wb') as pkl:
                    pickle.dump(im_net,pkl)
            else: # Load the precomputed data
                if verbose :print('We will load the precomputed bottleneck deep features :',name_pkl_values)
                with open(name_pkl_values, 'rb') as pkl:
                    features_net = pickle.load(pkl)
                
                with open(name_pkl_im, 'rb') as pkl:
                    im_net = pickle.load(pkl)
                
    if not(batch_size==32):
        batch_size_str =''
    else:
        batch_size_str ='_bs'+str(batch_size)
    AP_file  = name_base
    if kind_method=='TL':
        AP_file += '_'+final_clf
        if final_clf in ['MLP2','MLP1','MLP3']:
            AP_file += '_'+str(epochs)+batch_size_str+'_'+optimizer
            lr = opt_option[-1]
            AP_file += '_lr' +str(lr) 
            if return_best_model:
                AP_file += '_BestOnVal'
        if normalisation:
            AP_file +=  '_Norm' 
        if gridSearch:
            AP_file += '_GS'
        if final_clf in ['MLP2','MLP1','MLP3']:
            if not(regulOnNewLayer is None):
               AP_file += '_'+regulOnNewLayer
               if len(regulOnNewLayerParam)>0:
                   if regulOnNewLayer=='l1' or  regulOnNewLayer=='l1':
                       AP_file += '_'+  regulOnNewLayerParam[0]
                   elif regulOnNewLayer=='l1_l2':
                       AP_file += '_'+  regulOnNewLayerParam[0]+'_'+ regulOnNewLayerParam[1]
            if not(dropout is None):
                 AP_file += '_dropout'+str(dropout)
            if optimizer=='SGD':
                if nesterov:
                    AP_file += '_nes'
                if not(SGDmomentum==0.0):
                    AP_file += '_sgdm'+str(SGDmomentum)
            if optimizer=='RMSprop':
                if not(SGDmomentum==0.0):
                    AP_file += '_m'+str(SGDmomentum)
            if not(decay==0.0):
                AP_file += '_dec'+str(decay)
            if NoValidationSetUsed:
                AP_file +='_NoValidationSetUsed'
            if RandomValdiationSet:
                AP_file +='_RnDValSet'
    elif kind_method=='FT':
       AP_file += '_'+str(epochs)+batch_size_str
       if not(optimizer=='adam'):
           AP_file += '_'+optimizer
       if not(regulOnNewLayer is None):
           AP_file += '_'+regulOnNewLayer
           if len(regulOnNewLayerParam)>0:
               if regulOnNewLayer=='l1' or  regulOnNewLayer=='l1':
                   AP_file += '_'+  regulOnNewLayerParam[0]
               elif regulOnNewLayer=='l1_l2':
                   AP_file += '_'+  regulOnNewLayerParam[0]+'_'+ regulOnNewLayerParam[1]
       if not(dropout is None):
            AP_file += '_dropout'+str(dropout) 
       if optimizer=='SGD':
           if nesterov:
                AP_file += '_nes'
           if not(SGDmomentum==0.0):
                AP_file += '_sgdm'+str(SGDmomentum)
       if optimizer=='RMSprop':
           if not(SGDmomentum==0.0):
                AP_file += '_m'+str(SGDmomentum)
       if not(decay==0.0):
           AP_file += '_dec'+str(decay)
       if return_best_model:
           AP_file += '_BestOnVal'
       if NoValidationSetUsed:
           AP_file +='_NoValidationSetUsed'
       if RandomValdiationSet:
           AP_file +='_RnDValSet'
    
    if constrNet in ['ResNet50_ROWD','ResNet50_ROWD_CUMUL','ResNet50_BNRF'] and kind_method=='FT':
        # In the case of the fine tuning of the ResNet50_ROWD model with only some part freezing or not
        if type(pretrainingModif)==bool:
            if pretrainingModif==False:
                AP_file +=  '_wholePretrainedNetFreeze'
        else:
            if not(freezingType=='FromTop'):
                name_base += '_'+freezingType
            AP_file += '_unfreeze'+str(pretrainingModif)
    
    AP_file_base =  AP_file
    AP_file_pkl =AP_file_base+'_AP.pkl'
    APfilePath =  os.path.join(output_path,AP_file_pkl)
    if verbose: print(APfilePath)
    
    # TL or FT method
    if kind_method=='TL':
        Latex_str = constrNet 
        if style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
            Latex_str += ' Block1-5\_conv1'
        elif style_layers==['block1_conv1','block2_conv1']:
            Latex_str += ' Block1-2\_conv1' 
        elif style_layers==['block1_conv1']:
            Latex_str += ' Block1\_conv1' 
        else:
            for layer in style_layers:
                Latex_str += layer
        Latex_str += ' ' +features.replace('_','\_')
        Latex_str += ' ' + transformOnFinalLayer
        Latex_str += ' '+final_clf
        if final_clf=='LinearSVC': 
            if gridSearch:
                Latex_str += 'GS'
            else:
                Latex_str += ' no GS'
        if getBeforeReLU:
            Latex_str += ' BFReLU'
    elif kind_method=='FT':
        Latex_str = constrNet +' '+transformOnFinalLayer  + ' ep :' +str(epochs)
        if type(pretrainingModif)==bool:
            if not(pretrainingModif):
                Latex_str += ' All Freeze'
        else:
            Latex_str += ' Unfreeze '+str(pretrainingModif) + ' ' +freezingType
        if getBeforeReLU:
            Latex_str += ' BFReLU'
        if weights is None:
            Latex_str += ' RandInit'
    
    if (not(os.path.isfile(APfilePath)) or ReDo) and not(onlyReturnResult) or returnStatistics:
        
        if target_dataset=='Paintings':
            sLength = len(df_label[item_name])
            classes_vectors = np.zeros((sLength,num_classes))
            for i in range(sLength):
                for j in range(num_classes):
                    if( classes[j] in df_label['classe'][i]):
                        classes_vectors[i,j] = 1
            if kind_method=='FT':
                df_copy = df_label.copy()
                for j,c in enumerate(classes):
                    df_copy[c] = classes_vectors[:,j].astype(int)
                    #df_copy[c] = df_copy[c].apply(lambda x : bool(x))
                df_label = df_copy
                df_label_test = df_label[df_label['set']=='test']
            y_test = classes_vectors[df_label['set']=='test',:]
        elif target_dataset=='IconArt_v1':
            sLength = len(df_label[item_name])
            classes_vectors =  df_label[classes].values
            df_label_test = df_label[df_label['set']=='test']
            y_test = classes_vectors[df_label['set']=='test',:]
        elif target_dataset=='RASTA':
            sLength = len(df_label[item_name])
            classes_vectors =  df_label[classes].values
            df_label_test = df_label[df_label['set']=='test']
            y_test = classes_vectors[df_label['set']=='test',:]
        else:
            raise(NotImplementedError)
    
        if kind_method=='TL':
            # Get Train set in form of numpy array
            index_train = df_label['set']=='train'
            if not(forLatex) and verbose:
                print('trainval + test classes_vectors.shape',classes_vectors.shape)
                print('trainval + test features_net.shape',features_net.shape)
            X_train = features_net[index_train,:]
            y_train = classes_vectors[df_label['set']=='train',:]
            
            X_test= features_net[df_label['set']=='test',:]
            
            X_val = features_net[df_label['set']==str_val,:]
            y_val = classes_vectors[df_label['set']==str_val,:]
            
            Xtrainval = np.vstack([X_train,X_val])
            ytrainval = np.vstack([y_train,y_val])
            
            if normalisation:
                scaler = StandardScaler()
                Xtrainval = scaler.fit_transform(Xtrainval)
                X_test = scaler.transform(X_test)
                
            if returnFeatures:
                return(Xtrainval,ytrainval,X_test,y_test)
            
            if final_clf=='LinearSVC':
                dico_clf=TrainClassifierOnAllClass(Xtrainval,ytrainval,clf=final_clf,gridSearch=gridSearch)
                # Prediction
                dico_pred = PredictOnTestSet(X_test,dico_clf,clf=final_clf)
                metrics = evaluationScoreDict(y_test,dico_pred)
            elif final_clf in ['MLP2','MLP1','MLP3']:
                if gridSearch:
                    if final_clf=='MLP2':
                        builder_model = partial(MLP_model,num_of_classes=num_classes,optimizer=optimizer,\
                                          regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                          nesterov=nesterov,decay=decay,verbose=verbose)
                    if final_clf=='MLP3':
                        builder_model = partial(MLP_model,num_of_classes=num_classes,optimizer=optimizer,num_layers=3,\
                                          regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                          nesterov=nesterov,decay=decay,verbose=verbose)
                    elif final_clf=='MLP1':
                        builder_model = partial(Perceptron_model,num_of_classes=num_classes,optimizer=optimizer,\
                                                regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                                nesterov=nesterov,decay=decay,verbose=verbose)
                        
                    model = TrainMLPwithGridSearch(builder_model,Xtrainval,ytrainval,batch_size,epochs)
                    
                else:
                    
                    if final_clf=='MLP2':
                        model = MLP_model(num_of_classes=num_classes,optimizer=optimizer,lr=lr,\
                                          regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                          nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,verbose=verbose)
                    if final_clf=='MLP3':
                        model = MLP_model(num_of_classes=num_classes,optimizer=optimizer,lr=lr,num_layers=3,\
                                          regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                          nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,verbose=verbose)
                    elif final_clf=='MLP1':
                        model = Perceptron_model(num_of_classes=num_classes,optimizer=optimizer,lr=lr,\
                                                regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,\
                                                nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,verbose=verbose)
                    
                    model = TrainMLP(model,X_train,y_train,X_val,y_val,batch_size,epochs,\
                                 verbose=verbose,plotConv=plotConv,return_best_model=return_best_model,\
                                 NoValidationSetUsed=NoValidationSetUsed,RandomValdiationSet=RandomValdiationSet)
                predictions = model.predict(X_test, batch_size=1)
                metrics = evaluationScore(y_test,predictions)  
            else:
                print(final_clf,'doesn t exist')
                raise(NotImplementedError)
                
        elif kind_method=='FT':
            # We fineTune a VGG
            if constrNet=='VGG':
                getBeforeReLU = False
                model = VGG_baseline_model(num_of_classes=num_classes,pretrainingModif=pretrainingModif,
                                           transformOnFinalLayer=transformOnFinalLayer,weights=weights,
                                           optimizer=optimizer,opt_option=opt_option,freezingType=freezingType,
                                           final_clf=final_clf,final_layer=features,verbose=verbose,
                                           regulOnNewLayer=regulOnNewLayer,regulOnNewLayerParam=regulOnNewLayerParam
                                           ,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                
            elif constrNet=='VGGAdaIn':
                model = vgg_AdaIn(style_layers,num_of_classes=num_classes,weights=weights,\
                          transformOnFinalLayer=transformOnFinalLayer,getBeforeReLU=getBeforeReLU,\
                          final_clf=final_clf,final_layer=features,verbose=verbose,\
                          optimizer=optimizer,opt_option=opt_option,regulOnNewLayer=regulOnNewLayer,\
                          regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
              
            elif constrNet=='VGGBaseNormCoherentAdaIn':
                    # A more coherent way to compute the VGGBaseNormalisation
                    # We will pass the dataset several time through the net modify bit after bit to 
                    # get the coherent mean and std of the target domain
                    whatToload = 'varmean'
                    dict_stats_source = get_dict_stats(source_dataset,number_im_considered,style_layers,\
                           whatToload,saveformat='h5',getBeforeReLU=getBeforeReLU,set=set,Net='VGG',\
                           cropCenter=cropCenter,BV=BV)
                    # Compute the reference statistics
                    list_mean_and_std_source = compute_ref_stats(dict_stats_source,style_layers,type_ref='mean',\
                                                         imageUsed='all',whatToload =whatToload,
                                                         applySqrtOnVar=True)
                    target_number_im_considered = None
                    target_set = 'trainval'
                    dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(target_dataset,source_dataset,target_number_im_considered,\
                           style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                           getBeforeReLU=getBeforeReLU,target_set=target_set,\
                           applySqrtOnVar=True,cropCenter=cropCenter,BV=BV,verbose=verbose) # It also computes the reference statistics (mean,var)
                    
                    # We use the vgg_BaseNorm as the initialisation of the VGGAdaIn one 
                    # That means we allow to fine-tune the batch normalisation
                    
                    model = vgg_AdaIn(style_layers,num_of_classes=num_classes,weights=weights,\
                          transformOnFinalLayer=transformOnFinalLayer,getBeforeReLU=getBeforeReLU,\
                          final_clf=final_clf,final_layer=features,verbose=verbose,\
                          optimizer=optimizer,opt_option=opt_option,regulOnNewLayer=regulOnNewLayer,\
                          regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,nesterov=nesterov,\
                          SGDmomentum=SGDmomentum,decay=decay,\
                          list_mean_and_std_source=list_mean_and_std_source,list_mean_and_std_target=list_mean_and_std_target)
                
            elif constrNet=='VGGFRN':
                model = vgg_FRN(style_layers,num_of_classes=num_classes,weights=weights,\
                          transformOnFinalLayer=transformOnFinalLayer,getBeforeReLU=getBeforeReLU,\
                          final_clf=final_clf,final_layer=features,verbose=verbose,\
                          optimizer=optimizer,opt_option=opt_option,regulOnNewLayer=regulOnNewLayer,\
                          regulOnNewLayerParam=regulOnNewLayerParam,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                
            elif constrNet=='VGGAdaDBN':
                model = vgg_adaDBN(style_layers,num_of_classes=num_classes,\
                          transformOnFinalLayer=transformOnFinalLayer,getBeforeReLU=getBeforeReLU,verbose=verbose,\
                          weights=weights,final_layer=features,final_clf=final_clf,\
                          optimizer=optimizer,opt_option=opt_option,regulOnNewLayer=regulOnNewLayer,\
                          regulOnNewLayerParam=regulOnNewLayerParam,\
                          dbn_affine=dbn_affine,m_per_group=m_per_group,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
            
            elif constrNet=='VGGsuffleInStats':
                model = vgg_suffleInStats(style_layers,num_of_classes=num_classes,\
                          transformOnFinalLayer=transformOnFinalLayer,getBeforeReLU=getBeforeReLU,verbose=verbose,\
                          weights=weights,final_layer=features,final_clf=final_clf,\
                          optimizer=optimizer,opt_option=opt_option,regulOnNewLayer=regulOnNewLayer,\
                          regulOnNewLayerParam=regulOnNewLayerParam,\
                          dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,\
                          kind_of_shuffling=kind_of_shuffling)
            
            elif constrNet=='ResNet50':
                getBeforeReLU = False
                model = ResNet_baseline_model(num_of_classes=num_classes,pretrainingModif=pretrainingModif,
                                           transformOnFinalLayer=transformOnFinalLayer,weights=weights,opt_option=opt_option,\
                                           res_num_layers=50,final_clf=final_clf,verbose=verbose,\
                                           freezingType=freezingType,dropout=dropout,nesterov=nesterov,\
                                           SGDmomentum=SGDmomentum,decay=decay,optimizer=optimizer)
                    
            elif constrNet=='ResNet50AdaIn':
                getBeforeReLU = False
                model = ResNet_AdaIn(style_layers,final_layer=features,num_of_classes=num_classes,\
                                           transformOnFinalLayer=transformOnFinalLayer,weights=weights,\
                                           res_num_layers=50,final_clf=final_clf,verbose=verbose,opt_option=opt_option,
                                           dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,optimizer=optimizer)
                
            elif constrNet=='ResNet50_ROWD_CUMUL':
                # Refinement the batch normalisation : normalisation statistics
                # Once on the Whole train val Dataset on new dataset
                # In a cumulative way to be more efficient
                # Il faudrait peut etre mieux gerer les cas ou la variances est négatives
                list_mean_and_std_source = None
                target_number_im_considered = None
                whatToload = 'varmean'
                target_set = 'trainval'
                dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(
                        target_dataset,source_dataset,target_number_im_considered,\
                        style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                        getBeforeReLU=getBeforeReLU,target_set=target_set,\
                        applySqrtOnVar=True,Net=constrNet,cropCenter=cropCenter,\
                        BV=BV,cumulativeWay=True,verbose=verbose,useFloat32=useFloat32) # It also computes the reference statistics (mean,var)
                
                network_features_extraction = ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction(
                               style_layers,list_mean_and_std_target=list_mean_and_std_target,\
                               final_layer=features,\
                               transformOnFinalLayer=transformOnFinalLayer,res_num_layers=50,\
                               weights='imagenet')

                model = add_head_and_trainable(network_features_extraction,num_of_classes=num_classes,optimizer=optimizer,opt_option=opt_option,\
                             final_clf=final_clf,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,\
                             pretrainingModif=pretrainingModif,freezingType=freezingType,net_model=constrNet)
                    
            elif constrNet=='ResNet50_ROWD_CUMUL_AdaIn':
                # Refinement the batch normalisation : normalisation statistics
                # Once on the Whole train val Dataset on new dataset
                # In a cumulative way to be more efficient
                # Il faudrait peut etre mieux gerer les cas ou la variances est négatives
                list_mean_and_std_source = None
                target_number_im_considered = None
                whatToload = 'varmean'
                target_set = 'trainval'
                dict_stats_target,list_mean_and_std_target = get_dict_stats_BaseNormCoherent(
                        target_dataset,source_dataset,target_number_im_considered,\
                        style_layers,list_mean_and_std_source,whatToload,saveformat='h5',\
                        getBeforeReLU=getBeforeReLU,target_set=target_set,\
                        applySqrtOnVar=True,Net='ResNet50_ROWD_CUMUL',cropCenter=cropCenter,\
                        BV=BV,cumulativeWay=True,verbose=verbose,useFloat32=useFloat32) # It also computes the reference statistics (mean,var)
                
                network_features_extraction = ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction(
                               style_layers,list_mean_and_std_target=list_mean_and_std_target,\
                               final_layer=features,\
                               transformOnFinalLayer=transformOnFinalLayer,res_num_layers=50,\
                               weights='imagenet')

                model = add_head_and_trainable(network_features_extraction,num_of_classes=num_classes,optimizer=optimizer,opt_option=opt_option,\
                             final_clf=final_clf,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,\
                             AdaIn_mode=True,style_layers=style_layers)
                    
            elif constrNet=='ResNet50_BNRF':
                res_num_layers = 50
                network_features_extractionBNRF= get_ResNet_BNRefin(df=df_label,\
                                x_col=item_name,path_im=path_to_img,\
                                str_val=str_val,num_of_classes=len(classes),Net=constrNet,\
                                weights=weights,res_num_layers=res_num_layers,\
                                transformOnFinalLayer=transformOnFinalLayer,\
                                kind_method=kind_method,\
                                batch_size=batch_size_RF,momentum=momentum,\
                                num_epochs_BN=epochs_RF,output_path=output_path,\
                                cropCenter=cropCenter)
                
#                dict_stats_target,list_mean_and_std_target = extract_Norm_stats_of_ResNet(network_features_extractionBNRF,\
#                                                    res_num_layers=res_num_layers,model_type=constrNet)
#                # To the network name
#                K.clear_session()
#                s = tf.InteractiveSession()
#                K.set_session(s)
#                
#                network_features_extraction = ResNet_BaseNormOnlyOnBatchNorm_ForFeaturesExtraction(
#                               style_layers,list_mean_and_std_target=list_mean_and_std_target,\
#                               final_layer=features,\
#                               transformOnFinalLayer=transformOnFinalLayer,res_num_layers=res_num_layers,\
#                               weights='imagenet')
                
                model = add_head_and_trainable(network_features_extractionBNRF,num_of_classes=num_classes,optimizer=optimizer,opt_option=opt_option,\
                             final_clf=final_clf,dropout=dropout,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,\
                                 pretrainingModif=pretrainingModif,freezingType=freezingType,net_model=constrNet)
                    ## Non tester !!!
                
                
            else:
                print(constrNet,'is unkwon in the context of TL')
                raise(NotImplementedError)
            
        
            model_path = os.path.join(model_output_path,AP_file_base+'.h5')
            include_optimizer=False
        
            if returnStatistics: # We will load the model and return it
                model = load_model(model_path)
                return(model)
            
            model = FineTuneModel(model,dataset=target_dataset,df=df_label,\
                                    x_col=item_name,y_col=classes,path_im=path_to_img,\
                                    str_val=str_val,num_classes=len(classes),epochs=epochs,\
                                    Net=constrNet,plotConv=plotConv,batch_size=batch_size,cropCenter=cropCenter,\
                                    NoValidationSetUsed=NoValidationSetUsed,RandomValdiationSet=RandomValdiationSet)
            
            model.save(model_path,include_optimizer=include_optimizer)
            # Prediction
            predictions = predictionFT_net(model,df_test=df_label_test,x_col=item_name,\
                                           y_col=classes,path_im=path_to_img,Net=constrNet,\
                                           cropCenter=cropCenter)

            metrics = evaluationScore(y_test,predictions)    
            del model
            
        with open(APfilePath, 'wb') as pkl:
            pickle.dump(metrics,pkl)
                
            
    else:
        try:
            with open(APfilePath, 'rb') as pkl:
                metrics = pickle.load(pkl)
        except FileNotFoundError as e:
            if onlyReturnResult:
                metrics = None
                return(metrics)
            else:
                raise(e)
                
    if len(metrics)==5:
        AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class = metrics
    if len(metrics)==4:
        AP_per_class,P_per_class,R_per_class,P20_per_class = metrics
        F1_per_class = None
    
    if not(forLatex) and verbose:
        print(target_dataset,source_dataset,number_im_considered,final_clf,features,transformOnFinalLayer,\
              constrNet,kind_method,'GS',gridSearch,'norm',normalisation,'getBeforeReLU',getBeforeReLU,kind_method,\
              final_clf)
        print(style_layers)
    
    
#    print(Latex_str)
    #VGGInNorm Block1-5\_conv1 fc2 LinearSVC no GS BFReLU
    str_part2 = arrayToLatex(AP_per_class,per=True)
    Latex_str += str_part2
    Latex_str = Latex_str.replace('\hline','')
    if verbose: print(Latex_str)
    
    # To clean GPU memory
    K.clear_session()
    gc.collect()
    #cuda.select_device(0)
    #cuda.close()
    
    return(AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class)

def get_ResNet_BNRefin(df,x_col,path_im,str_val,num_of_classes,Net,\
                       weights,res_num_layers,transformOnFinalLayer,kind_method,\
                       batch_size=16,momentum=0.9,num_epochs_BN=5,output_path='',cropCenter=False):
    """
    This function refine the normalisation statistics of the batch normalisation 
    with an exponential moving average
    
    Le fait que les valeurs explosent et donnent nan vient peut etre de la : 
        https://github.com/keras-team/keras/issues/11927#issuecomment-568863705
    """
    
    model_file_name = 'ResNet'+str(res_num_layers)+'_BNRF_'+str(weights)+'_'+transformOnFinalLayer+\
        '_bs' +str(batch_size)+'_m'+str(momentum)+'_ep'+str(num_epochs_BN) 
    if cropCenter:
        model_file_name += '_cropCenter'
    model_file_name_path = model_file_name + '.tf'
    model_file_name_path = os.path.join(output_path,'model',model_file_name_path) 
    model_file_name_path_for_test_existence = os.path.join(output_path,'model',model_file_name_path) +'.index'
    
    print('model_file_name_path',model_file_name_path_for_test_existence,'it is exist ? ',os.path.isfile(model_file_name_path_for_test_existence))
    verbose = True
    model = ResNet_BNRefinements_Feat_extractor(num_of_classes=num_of_classes,\
                                            transformOnFinalLayer =transformOnFinalLayer,\
                                            verbose=verbose,weights=weights,\
                                            res_num_layers=res_num_layers,momentum=momentum,\
                                            kind_method=kind_method)
    
    # model = ResNet_cut(final_layer='activation_48',\
    #                     transformOnFinalLayer =transformOnFinalLayer,\
    #                     verbose=verbose,weights=weights,res_num_layers=res_num_layers)
    
    model.trainable = True
    
    print('Before all')
    name_layer = 'bn_conv1'
    batchnorm_layer = model.get_layer(name_layer)
    moving_mean = batchnorm_layer.moving_mean
    moving_variance = batchnorm_layer.moving_variance
    moving_mean_eval = tf.keras.backend.eval(moving_mean)
    moving_std_eval = np.sqrt(tf.keras.backend.eval(moving_variance))
    mean_and_std_layer = moving_mean_eval,moving_std_eval
    print(name_layer)
    print(mean_and_std_layer)
    
    if os.path.isfile(model_file_name_path_for_test_existence):
        print('--- We will load the weights of the model ---')
        #model = load_model(model_file_name_path)
        model.trainable = False
        model.load_weights(model_file_name_path)
    else:
        print('--- We will refine the normalisation parameters ---')
        
        if cropCenter:
            interpolation='lanczos:center'
            old_loading_img_fct = kp.image.iterator.load_img
            kp.image.iterator.load_img = partial(load_and_crop_img_forImageGenerator,Net=Net)
        else:
            interpolation='nearest'
        if 'VGG' in Net:
            preprocessing_function = tf.keras.applications.vgg19.preprocess_input
            target_size = (224,224)
        elif 'ResNet50' in Net:
            preprocessing_function = tf.keras.applications.resnet50.preprocess_input
            target_size = (224,224)
        else:
            print(Net,'is unknwon')
            raise(NotImplementedError)
    
        df_train = df[df['set']=='train']
        df_val = df[df['set']==str_val]
        df_train[x_col] = df_train[x_col].apply(lambda x : x + '.jpg')
        df_val[x_col] = df_val[x_col].apply(lambda x : x + '.jpg')
        if not(len(df_val)==0):
            df_train = df_train.append(df_val)
            
        datagen= tf.keras.preprocessing.image.ImageDataGenerator(preprocessing_function=preprocessing_function)
        # Todo should add the possibility to crop the center of the image here
        trainval_generator=datagen.flow_from_dataframe(dataframe=df_train, directory=path_im,\
                                                    x_col=x_col,y_col=None,\
                                                    class_mode=None, \
                                                    target_size=target_size, batch_size=batch_size,\
                                                    shuffle=True,\
                                                    interpolation=interpolation)
        STEP_SIZE_TRAIN=trainval_generator.n//trainval_generator.batch_size
                
        use_multiprocessing =  True
        workers = 8
        max_queue_size = 20
        
        model =  fit_generator_ForRefineParameters_v2(model,
                      trainval_generator,
                      steps_per_epoch=STEP_SIZE_TRAIN,
                      epochs=num_epochs_BN,
                      verbose=1,
                      max_queue_size=max_queue_size,
                      workers=workers,
                      use_multiprocessing=use_multiprocessing,
                      shuffle=True)

        model.trainable = False
        model.save_weights(model_file_name_path)
        
        if cropCenter:
            kp.image.iterator.load_img = old_loading_img_fct

    return(model)

class FirstLayerBNStatsPrintingCallback(tf.keras.callbacks.Callback):

  def on_train_batch_end(self, batch, logs=None):
      batchnorm_layer = self.model.get_layer('bn_conv1')
      moving_mean = batchnorm_layer.moving_mean
      moving_variance = batchnorm_layer.moving_variance
      moving_mean_eval = tf.keras.backend.eval(moving_mean)
      moving_std_eval = np.sqrt(tf.keras.backend.eval(moving_variance))
      print('For batch {}, moving_mean is {} moving std {}.'.format(batch, moving_mean_eval,moving_std_eval))


def FineTuneModel(model,dataset,df,x_col,y_col,path_im,str_val,num_classes,epochs=20,\
                  Net='VGG',batch_size = 16,plotConv=False,test_size=0.15,\
                  return_best_model=False,cropCenter=False,NoValidationSetUsed=False,\
                  RandomValdiationSet=False):
    """
    To fine tune a deep model
    @param x_col : name of images
    @param y_col : classes
    @param path_im : path to images
    @param : return_best_model : return the best model on the val_loss
    """
    assert(not(NoValidationSetUsed and return_best_model))
    
    df_train = df[df['set']=='train']
    df_val = df[df['set']==str_val]
    df_train[x_col] = df_train[x_col].apply(lambda x : x + '.jpg')
    df_val[x_col] = df_val[x_col].apply(lambda x : x + '.jpg')
    
    if RandomValdiationSet:
        df_train = df_train.append(df_val)

    if not(NoValidationSetUsed):
        if len(df_val)==0:
            df_train, df_val = train_test_split(df_train, test_size=test_size)
    else:
        df_train = df_train.append(df_val)
        
    if cropCenter:
        interpolation='lanczos:center'
        old_loading_img_fct = kp.image.iterator.load_img
        kp.image.iterator.load_img = partial(load_and_crop_img_forImageGenerator,Net=Net)
    else:
        interpolation='nearest'
    if 'VGG' in Net:
        preprocessing_function = tf.keras.applications.vgg19.preprocess_input
        target_size = (224,224)
    elif 'ResNet50' in Net:
        preprocessing_function = tf.keras.applications.resnet50.preprocess_input
        target_size = (224,224)
    else:
        print(Net,'is unknwon')
        raise(NotImplementedError)
            
    datagen= tf.keras.preprocessing.image.ImageDataGenerator(preprocessing_function=preprocessing_function)    
    # preprocessing_function will be implied on each input. The function will run after the image is 
    # load resized and augmented. That's why we need to modify the load_img fct
    
    
    train_generator=datagen.flow_from_dataframe(dataframe=df_train, directory=path_im,\
                                                x_col=x_col,y_col=y_col,\
                                                class_mode="other", \
                                                target_size=target_size, batch_size=batch_size,\
                                                shuffle=True,\
                                                interpolation=interpolation)
    STEP_SIZE_TRAIN=train_generator.n//train_generator.batch_size
    
    if not(NoValidationSetUsed):
        validate_datagen = tf.keras.preprocessing.image.ImageDataGenerator(preprocessing_function=preprocessing_function)
        valid_generator=validate_datagen.flow_from_dataframe(dataframe=df_val, directory=path_im,\
                                                    x_col=x_col,y_col=y_col,\
                                                    class_mode="other", \
                                                    target_size=target_size, batch_size=batch_size,\
                                                    interpolation=interpolation)
        STEP_SIZE_VALID=valid_generator.n//valid_generator.batch_size
    
    
    # TODO you should add an early stoppping 
#    earlyStopping = EarlyStopping(monitor='val_loss', patience=10, verbose=0, mode='min')
#    mcp_save = ModelCheckpoint('.mdl_wts.hdf5', save_best_only=True, monitor='val_loss', mode='min')
#    reduce_lr_loss = ReduceLROnPlateau(monitor='val_loss', factor=0.1, patience=7, verbose=1, epsilon=1e-4, mode='min')
#    
    #callbacks = [FirstLayerBNStatsPrintingCallback()] # To print the moving mean and std at each batch
    callbacks = []
    if return_best_model:
        tmp_model_path = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + '.h5')
        mcp_save = ModelCheckpoint(tmp_model_path, save_best_only=True, monitor='val_loss', mode='min')
        callbacks += [mcp_save]
        
    workers=8
    use_multiprocessing = True
    if not(NoValidationSetUsed):
        history = model.fit_generator(generator=train_generator,
                        steps_per_epoch=STEP_SIZE_TRAIN,
                        validation_data=valid_generator,
                        validation_steps=STEP_SIZE_VALID,
                        epochs=epochs,use_multiprocessing=use_multiprocessing,
                        workers=workers,callbacks=callbacks)
    else:
        history = model.fit_generator(generator=train_generator,
                        steps_per_epoch=STEP_SIZE_TRAIN,
                        epochs=epochs,use_multiprocessing=use_multiprocessing,
                        workers=workers,callbacks=callbacks)
    
    if return_best_model: # We need to load back the best model !
        # https://github.com/keras-team/keras/issues/2768
        model = load_model(tmp_model_path) 
    
    if plotConv:
       plotKerasHistory(history) 
       
    if cropCenter:
        kp.image.iterator.load_img = old_loading_img_fct
        
    return(model)

def plotKerasHistory(history):
    plt.ion()
    plt.figure()
    plt.plot(history.history['loss'], label='train')
    plt.plot(history.history['val_loss'], label='val')
    plt.title('Loss')
    plt.legend()
    plt.figure()
    plt.plot(history.history['acc'], label='train')
    plt.plot(history.history['val_acc'], label='val')
    plt.title('Acc')
    plt.legend()
    plt.draw()
    plt.pause(0.001)
   
    
def TrainMLP(model,X_train,y_train,X_val,y_val,batch_size,epochs,verbose=False,\
             plotConv=False,return_best_model=False,NoValidationSetUsed=False,RandomValdiationSet=False,
             validation_split_init=0.15):
    """
    @param : NoValidationSetUsed if True : we will not use the predetermined dataset
    @param : plotConv : convergence plotting
    """
    assert(not(NoValidationSetUsed and return_best_model))
    
    callbacks = []
    if return_best_model:
        tmp_model_path = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + '.h5')
        mcp_save = ModelCheckpoint(tmp_model_path, save_best_only=True, monitor='val_loss',\
                                   mode='min')
        callbacks += [mcp_save]
    
    workers = 8
    use_multiprocessing = True
    
    STEP_SIZE_TRAIN=len(X_train)//batch_size
    if (not(len(X_val)==0) and not(NoValidationSetUsed)) and not(RandomValdiationSet):
        STEP_SIZE_VALID=len(X_val)//batch_size
        history = model.fit(X_train, y_train,batch_size=batch_size,epochs=epochs,\
                            validation_data=(X_val, y_val),\
                            steps_per_epoch=STEP_SIZE_TRAIN,
                            #validation_steps=STEP_SIZE_VALID,\
                            use_multiprocessing=use_multiprocessing,workers=workers,\
                            shuffle=True,callbacks=callbacks)
    else: # No validation set provided
        if NoValidationSetUsed:
            validation_split = 0.0
        else:
            validation_split = validation_split_init
        history = model.fit(X_train, y_train,batch_size=batch_size,epochs=epochs,\
                            validation_split=validation_split,\
                            steps_per_epoch=STEP_SIZE_TRAIN,\
                            use_multiprocessing=use_multiprocessing,workers=workers,\
                            shuffle=True,callbacks=callbacks)
    if plotConv: # Plot convergence  
        plotKerasHistory(history)
    if verbose: print(model.summary())   
    return(model)
    
def TrainMLPwithGridSearch(builder_model,X,Y,batch_size,epochs):
    """
    Train the MLP with a grid search on learning rate and momentum
    """
    print('Train MLP with Grid search')
    learn_rate = [0.0001,0.001, 0.01, 0.1, 0.2, 0.3]
    momentum = [0.0, 0.2, 0.4, 0.6, 0.8, 0.9]
    # TODO faire un test avec momentum pour le SGD mais pas pour adam
    param_grid = dict(lr=learn_rate, SGDmomentum=momentum)
    print(param_grid)
    print(builder_model)

    w_model = tf.keras.wrappers.scikit_learn.KerasClassifier(build_fn=builder_model, epochs=epochs, 
                                                             batch_size=batch_size,verbose=0)
    grid = GridSearchCV(estimator=w_model, param_grid=param_grid, n_jobs=-1, cv=3,
                        refit=True,scoring =make_scorer(average_precision_score,needs_threshold=True))
    model = grid.fit(X, Y)
    return(model)
    
def predictionFT_net(model,df_test,x_col,y_col,path_im,Net='VGG',cropCenter=False):
    """
    This function predict on tht provide test set for a fine-tuned network
    """
    df_test[x_col] = df_test[x_col].apply(lambda x : x + '.jpg')
    
    if cropCenter:
        interpolation='lanczos:center'
        old_loading_img_fct = kp.image.iterator.load_img
        kp.image.iterator.load_img = partial(load_and_crop_img_forImageGenerator,Net=Net)
    else:
        interpolation='nearest'
    if 'VGG' in Net:
        preprocessing_function = tf.keras.applications.vgg19.preprocess_input
        target_size = (224,224)
    elif 'ResNet50' in Net:
        preprocessing_function = tf.keras.applications.resnet50.preprocess_input
        target_size = (224,224)
    else:
        print(Net,'is unknwon')
        raise(NotImplementedError)
            
    use_multiprocessing = True
    workers = 8
    batch_size = 16
        
    datagen= tf.keras.preprocessing.image.ImageDataGenerator(preprocessing_function=preprocessing_function)    
    test_generator=datagen.flow_from_dataframe(dataframe=df_test, directory=path_im,\
                                                x_col=x_col,\
                                                class_mode=None,shuffle=False,\
                                                target_size=target_size, batch_size=batch_size,\
                                                use_multiprocessing=use_multiprocessing,workers=workers,\
                                                interpolation=interpolation)
    predictions = model.predict_generator(test_generator)
    
    if cropCenter:
        kp.image.iterator.load_img = old_loading_img_fct
        
    return(predictions)
    
def evaluationScoreDict(y_gt,dico_pred,verbose=False,k = 20,seuil=0.5):
    """
    @param k for precision at rank k
    @param the seuil can change a lot of things on the F1 score
    """
    num_samples,num_classes = y_gt.shape
    AP_per_class = []
    P_per_class = []
    R_per_class = []
    F1_per_class = []
    P20_per_class = []
    for c in range(num_classes):
        y_gt_c = y_gt[:,c]
        [y_predict_confidence_score,y_predict_test] = dico_pred[c]
        AP = average_precision_score(y_gt_c,y_predict_confidence_score,average=None)
        if verbose: print("Average Precision on all the data for classe",c," = ",AP)  
        AP_per_class += [AP] 
        test_precision = precision_score(y_gt_c,y_predict_test)
        test_recall = recall_score(y_gt_c,y_predict_test)
        R_per_class += [test_recall]
        P_per_class += [test_precision]
        F1 = f1_score(y_gt_c,y_predict_test)
        F1_per_class +=[F1]
        precision_at_k = ranking_precision_score(np.array(y_gt_c), y_predict_confidence_score,k)
        P20_per_class += [precision_at_k]
        if verbose: print("Test on all the data precision = {0:.2f}, recall = {1:.2f}, F1 = {2:.2f}, precision a rank k=20  = {3:.2f}.".format(test_precision,test_recall,F1,precision_at_k))
    return(AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class)
    
def evaluationScore(y_gt,y_pred,verbose=False,k = 20,seuil=0.5):
    """
    y_gt must be between 0 or 1
    y_predmust be between 0 and 1
    @param k for precision at rank k
    @param the seuil can change a lot of things
    """
    num_samples,num_classes = y_gt.shape
    AP_per_class = []
    P_per_class = []
    F1_per_class = []
    R_per_class = []
    P20_per_class = []
    for c in range(num_classes):
        y_gt_c = y_gt[:,c]
        y_predict_confidence_score = y_pred[:,c] # The prediction by the model
        y_predict_test = (y_predict_confidence_score>seuil).astype(int)
        if verbose:
            print('classe num',c)
            print('GT',y_gt_c)
            print('Pred',y_predict_confidence_score)
        AP = average_precision_score(y_gt_c,y_predict_confidence_score,average=None)
        if verbose: print("Average Precision ofpickn all the data for classe",c," = ",AP)  
        AP_per_class += [AP] 
        test_precision = precision_score(y_gt_c,y_predict_test)
        test_recall = recall_score(y_gt_c,y_predict_test)
        R_per_class += [test_recall]
        P_per_class += [test_precision]
        F1 = f1_score(y_gt_c,y_predict_test)
        F1_per_class +=[F1]
        precision_at_k = ranking_precision_score(np.array(y_gt_c), y_predict_confidence_score,k)
        P20_per_class += [precision_at_k]
        if verbose: print("Test on all the data precision = {0:.2f}, recall = {1:.2f}, F1 = {2:.2f}, precision a rank k=20  = {3:.2f}.".format(test_precision,test_recall,F1,precision_at_k))
    return(AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class)

def RunUnfreezeLayerPerformanceVGG(plot=False):
    """
    The goal is to unfreeze only some part of the network
    """
    list_freezingType = ['FromTop','FromBottom','Alter']
    
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D','']
    optimizer_tab = ['adam','SGD']
    opt_option_tab = [[0.01],[0.1,0.01]]
    range_l = range(0,17)
    target_dataset = 'Paintings'
    for transformOnFinalLayer in transformOnFinalLayer_tab:
        for optimizer,opt_option in zip(optimizer_tab,opt_option_tab):
            if plot: plt.figure()
            list_perf = [] 
            j = 0
            for freezingType in list_freezingType:
                list_perf += [[]]  
                for pretrainingModif in range_l:
                    metrics = learn_and_eval(target_dataset=target_dataset,constrNet='VGG',\
                                             kind_method='FT',epochs=20,transformOnFinalLayer=transformOnFinalLayer,\
                                             pretrainingModif=pretrainingModif,freezingType=freezingType,
                                             optimizer=optimizer,opt_option=opt_option)

        
                    AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class = metrics
                    list_perf[j] += [np.mean(AP_per_class)]
                if plot: plt.plot(list(range_l),list_perf[j],label=freezingType)
                j += 1
            if plot:
                title = optimizer + ' ' + transformOnFinalLayer
                plt.xlabel('Number of layers retrained')
                plt.ylabel('mAP ArtUK')
                plt.title(title)
                plt.legend(loc='best')
                output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',target_dataset,'fig')
                pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
                fname =  os.path.join(output_path,target_dataset+'_Unfreezed_'+ optimizer+'_'+transformOnFinalLayer+'.png')
                plt.show() 
                plt.savefig(fname)
                plt.close()
                
def PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'Paintings',short=False,
                           scenario=0,onlyPlot=False,BV=True,cropCenter=True):
    """
    Plot some mAP  on ArtUK Paintings dataset with different model just to see
    if we can say someting
    """
    # Normally metric = AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class but sometimes F1 is missing
    if metricploted=='mAP':
        metricploted_index = 0
    elif metricploted=='Precision':
        metricploted_index = 1
    elif metricploted=='Recall':
        metricploted_index = 2
    else:
        print(metricploted,' is unknown')
        raise(NotImplementedError)
        
    list_markers = ['o','s','X','*','v','^','<','>','d','1','2','3','4','8','h','H','p','d','$f$','P']
    # Les 3 frozen : 'o','s','X'
    # VGG : '*'
    
    NUM_COLORS = 20
    color_number_for_frozen = [0,NUM_COLORS//2,NUM_COLORS-1]
    cm = plt.get_cmap('gist_rainbow')
    cNorm  = colors.Normalize(vmin=0, vmax=NUM_COLORS-1)
    scalarMap = mplcm.ScalarMappable(norm=cNorm, cmap=cm)
    list_freezingType = ['FromTop','FromBottom','Alter']
    #list_freezingType = ['FromTop']
    
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D'] # Not the flatten case for the moment
    #transformOnFinalLayer_tab = ['GlobalMaxPooling2D'] # Not the flatten case for the moment
    
    dropout=None
    regulOnNewLayer=None
    nesterov=False
    SGDmomentum=0.0
    decay=0.0
    if scenario==0:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD','adam']
        opt_option_tab = [[0.1,0.001],[0.01]] # Soit 0=10**-3
        return_best_model = False
    elif scenario==1:
        final_clf = 'MLP1'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
    elif scenario==2:
        final_clf = 'MLP1'
        epochs = 100
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-5)]]
        return_best_model = True
        # Really small learning rate 10**(-5)
    elif scenario==3:
        final_clf = 'MLP1'
        epochs = 5
        optimizer_tab = ['adam']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
        # Really small learning rate 10**(-5)
    elif scenario==4:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
    elif scenario==5:
        final_clf = 'MLP1'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,0.01]] # WILDACT
        return_best_model = True
    elif scenario==6:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
        dropout=0.2
        regulOnNewLayer='l2'
        nesterov=True
        SGDmomentum=0.99
        decay=0.0005
    elif scenario==7:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
        dropout=0.5
        SGDmomentum=0.99
        decay=0.0005
    elif scenario==8:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
        dropout=0.5
        SGDmomentum=0.9
    elif scenario==9:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[10**(-2)]]
        return_best_model = True
    elif scenario==10:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-2)]]
        return_best_model = True
    elif scenario==11:
        final_clf = 'MLP2'
        epochs = 50
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
    else:
        raise(NotImplementedError)
    
    # Not the flatten case for the moment
#    optimizer_tab = ['SGD','SGD','adam']
#    opt_option_tab = [[0.1,0.01],[0.1,0.001],[0.01]]
#    optimizer_tab = ['SGD','adam']
    
    range_l = range(0,17)
    
    if short:
        transformOnFinalLayer_tab = ['GlobalMaxPooling2D']
        range_l = range(0,6)
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,0.001]]
        list_freezingType = ['FromTop']
#    opt_option_tab = [[0.1,0.01]]
#    optimizer_tab = ['SGD']
    for optimizer,opt_option in zip(optimizer_tab,opt_option_tab): 
        for transformOnFinalLayer in transformOnFinalLayer_tab:
            fig_i = 0
            plt.figure()
            list_perf = [] 
            j = 0
            # Plot the value with a certain number of freeze or unfreeze layer
            for freezingType in list_freezingType:
                list_perf += [[]]  
                for pretrainingModif in range_l:
                    metrics = learn_and_eval(target_dataset=target_dataset,constrNet='VGG',\
                                             kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                             pretrainingModif=pretrainingModif,freezingType=freezingType,
                                             optimizer=optimizer,opt_option=opt_option,cropCenter=cropCenter
                                             ,final_clf=final_clf,features='block5_pool',\
                                             return_best_model=return_best_model,onlyReturnResult=onlyPlot,\
                                             dropout=dropout,regulOnNewLayer=regulOnNewLayer,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
    
                    if metrics is None:
                        continue
                    metricI_per_class = metrics[metricploted_index]
                    list_perf[j] += [np.mean(metricI_per_class)]
                if not(len(list(range_l))==len(list_perf[j])):
                    layers_j = list(range_l)[0:len(list_perf[j])]
                else:
                    layers_j = list(range_l)

                plt.plot(layers_j,list_perf[j],label=freezingType,color=scalarMap.to_rgba(color_number_for_frozen[fig_i]),\
                         marker=list_markers[fig_i],linestyle=':')
                fig_i += 1
                j += 1
            
            if short:
                continue
#            # Plot other proposed solution
#            features = 'block5_pool'
#            net_tab = ['VGG','VGGInNorm','VGGInNormAdapt','VGGBaseNorm','VGGBaseNormCoherent']
#            style_layers_tab_forOther = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
#                             ['block1_conv1','block2_conv1'],['block1_conv1']]
#            style_layers_tab_foVGGBaseNormCoherentr = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
#                             ['block1_conv1','block2_conv1']]
#            number_im_considered = 1000
#            source_dataset = 'ImageNet'
#            kind_method = 'TL'
#            normalisation = False
            getBeforeReLU = True
#            forLatex = True
#            fig_i = 0
#            for constrNet in net_tab:
#                print(constrNet)
#                if constrNet=='VGGBaseNormCoherent':
#                    style_layers_tab = style_layers_tab_foVGGBaseNormCoherentr
#                elif constrNet=='VGG':
#                    style_layers_tab = [[]]
#                else:
#                    style_layers_tab = style_layers_tab_forOther
#                for style_layers in style_layers_tab:
#                    labelstr = constrNet 
#                    if not(constrNet=='VGG'):
#                        labelstr += '_'+ numeral_layers_index(style_layers)
#                    metrics = learn_and_eval(target_dataset,source_dataset,final_clf=final_clf,features='block5_pool',\
#                                       constrNet=constrNet,kind_method=kind_method,style_layers=style_layers,gridSearch=False,
#                                       number_im_considered=number_im_considered,
#                                       normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
#                                       transformOnFinalLayer=transformOnFinalLayer,\
#                                       optimizer=optimizer,opt_option=[opt_option[-1]],\
#                                       forLatex=forLatex,epochs=epochs,return_best_model=return_best_model,\
#                                       onlyReturnResult=onlyPlot)
#                    
#                    if metrics is None:
#                        continue
#                    
#                    metricI_per_class = metrics[metricploted_index]
#                    mMetric = np.mean(metricI_per_class)
#                    if fig_i in color_number_for_frozen:
#                        fig_i_c = fig_i +1 
#                        fig_i_m = fig_i
#                        fig_i += 1
#                    else:
#                        fig_i_c = fig_i
#                        fig_i_m = fig_i
#                    plt.plot([0],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
#                             marker=list_markers[fig_i_m],linestyle='')
#                    fig_i += 1
            
            # Case of the fine tuning with batch normalization 
            constrNet = 'VGGAdaIn'
            style_layers_tab_VGGAdaIn = [['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4'],
                                                        ['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                                                        ['block1_conv1','block2_conv1'],['block2_conv1'],['block1_conv1']]
       
            for style_layers in style_layers_tab_VGGAdaIn:
    #            print(constrNet,style_layers)
                metrics = learn_and_eval(target_dataset,constrNet=constrNet,kind_method='FT',\
                                          epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                          forLatex=True,optimizer=optimizer,\
                                          opt_option=[opt_option[-1]],cropCenter=cropCenter,\
                                          style_layers=style_layers,getBeforeReLU=getBeforeReLU,\
                                          final_clf=final_clf,features='block5_pool',return_best_model=return_best_model,\
                                          onlyReturnResult=onlyPlot,\
                                          dropout=dropout,regulOnNewLayer=regulOnNewLayer,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                
                if metrics is None:
                    continue
                
                metricI_per_class = metrics[metricploted_index]
                mMetric = np.mean(metricI_per_class)
                if fig_i in color_number_for_frozen:
                    fig_i_c = fig_i +1 
                    fig_i_m = fig_i
                    fig_i += 1
                else:
                    fig_i_c = fig_i
                    fig_i_m = fig_i
                labelstr = constrNet 
                if not(constrNet=='VGG'):
                    if BV:
                        if style_layers==['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4']:
                            
                            labelstr += '_all'
                        elif style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
                            labelstr += '*conv1' 
                        elif style_layers==['block1_conv1','block2_conv1']:
                            labelstr += 'b1_b2_conv1' 
                        elif style_layers==['block1_conv1']:
                            labelstr += 'b1_conv1' 
                        else:
                            labelstr += '_'+ numeral_layers_index_bitsVersion(style_layers)
                    else:
                        labelstr += '_'+ numeral_layers_index(style_layers)
                x = len(style_layers)
                plt.plot([x],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
                         marker=list_markers[fig_i_m],linestyle='')
                fig_i += 1
                
            # Case of the fine tuning with an other kind of batch normalisation VGGFRN
            constrNet = 'VGGFRN'
            style_layers_tab_VGGAdaIn = [['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4'],
                                                        ['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                                                        ['block1_conv1','block2_conv1'],['block2_conv1'],['block1_conv1']]
       
            for style_layers in style_layers_tab_VGGAdaIn:
    #            print(constrNet,style_layers)
                metrics = learn_and_eval(target_dataset,constrNet=constrNet,kind_method='FT',\
                                          epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                          forLatex=True,optimizer=optimizer,\
                                          opt_option=[opt_option[-1]],cropCenter=cropCenter,\
                                          style_layers=style_layers,getBeforeReLU=getBeforeReLU,\
                                          final_clf=final_clf,features='block5_pool',return_best_model=return_best_model,\
                                          onlyReturnResult=onlyPlot,\
                                          dropout=dropout,regulOnNewLayer=regulOnNewLayer,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                
                if metrics is None:
                    continue
                
                metricI_per_class = metrics[metricploted_index]
                mMetric = np.mean(metricI_per_class)
                if fig_i in color_number_for_frozen:
                    fig_i_c = fig_i +1 
                    fig_i_m = fig_i
                    fig_i += 1
                else:
                    fig_i_c = fig_i
                    fig_i_m = fig_i
                labelstr = constrNet 
                if not(constrNet=='VGG'):
                    if BV:
                        if style_layers==['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4']:
                            
                            labelstr += '_all'
                        elif style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
                            labelstr += '*conv1' 
                        elif style_layers==['block1_conv1','block2_conv1']:
                            labelstr += 'b1_b2_conv1' 
                        elif style_layers==['block1_conv1']:
                            labelstr += 'b1_conv1' 
                        else:
                            labelstr += '_'+ numeral_layers_index_bitsVersion(style_layers)
                    else:
                        labelstr += '_'+ numeral_layers_index(style_layers)
                x = len(style_layers)
                plt.plot([x],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
                         marker=list_markers[fig_i_m],linestyle='')
                fig_i += 1
                
            # Case of the fine tuning with batch normalization  with the BaseCoherent initialisation

                
            # Case of the fine tuning with decorellated batch normalization 
            # TODO a debugguer
#            constrNet = 'VGGAdaDBN'
#            style_layers_tab_VGGAdaDBN = [['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
#                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
#                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
#                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4'],
#                                                        ['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
#                                                        ['block1_conv1','block2_conv1'],['block2_conv1'],['block1_conv1']]
#            for style_layers in style_layers_tab_VGGAdaDBN:
#    #            print(constrNet,style_layers)
#                metrics = learn_and_eval(target_dataset,constrNet=constrNet,kind_method='FT',\
#                                          epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
#                                          forLatex=True,optimizer=optimizer,\
#                                          opt_option=[opt_option[-1]],cropCenter=cropCenter,\
#                                          style_layers=style_layers,getBeforeReLU=getBeforeReLU,\
#                                          final_clf=final_clf,features='block5_pool',return_best_model=return_best_model,\
#                                          onlyReturnResult=onlyPlot,dbn_affine=True,m_per_group=16,\
#                                          dropout=dropout,regulOnNewLayer=regulOnNewLayer,nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
#                
#                if metrics is None:
#                    continue
#                
#                metricI_per_class = metrics[metricploted_index]
#                mMetric = np.mean(metricI_per_class)
#                if fig_i in color_number_for_frozen:
#                    fig_i_c = fig_i +1 
#                    fig_i_m = fig_i
#                    fig_i += 1
#                else:
#                    fig_i_c = fig_i
#                    fig_i_m = fig_i
#                labelstr = constrNet 
#                if not(constrNet=='VGG'):
#                    if BV:
#                        labelstr += '_'+ numeral_layers_index_bitsVersion(style_layers)
#                    else:
#                        labelstr += '_'+ numeral_layers_index(style_layers)
#                plt.plot([0],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
#                         marker=list_markers[fig_i_m],linestyle='')
#                fig_i += 1
#                
            # Case of tthe stats (mean,var) shuffling
            constrNet = 'VGGsuffleInStats'
            style_layers_tab_VGGAdaDBN = [['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4'],
                                                        ['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                                                        ['block1_conv1','block2_conv1'],['block2_conv1'],['block1_conv1']]
            
            kind_of_shuffling_tab=['roll','shuffle']
            for kind_of_shuffling in kind_of_shuffling_tab:
                for style_layers in style_layers_tab_VGGAdaDBN:
        #            print(constrNet,style_layers)
                    metrics = learn_and_eval(target_dataset,constrNet=constrNet,kind_method='FT',\
                                              epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                              forLatex=True,optimizer=optimizer,\
                                              opt_option=[opt_option[-1]],cropCenter=cropCenter,\
                                              style_layers=style_layers,getBeforeReLU=getBeforeReLU,\
                                              final_clf=final_clf,features='block5_pool',return_best_model=return_best_model,\
                                              onlyReturnResult=onlyPlot,\
                                              dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                              nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,\
                                              kind_of_shuffling=kind_of_shuffling)
                    
                    if metrics is None:
                        continue
                    
                    metricI_per_class = metrics[metricploted_index]
                    mMetric = np.mean(metricI_per_class)
                    if fig_i in color_number_for_frozen:
                        fig_i_c = fig_i +1 
                        fig_i_m = fig_i
                        fig_i += 1
                    else:
                        fig_i_c = fig_i
                        fig_i_m = fig_i
                    labelstr = constrNet 
                    if not(constrNet=='VGG'):
                        if BV:
                            if style_layers==['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4']:
                            
                                labelstr += '_all'
                            elif style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
                                labelstr += '*conv1' 
                            elif style_layers==['block1_conv1','block2_conv1']:
                                labelstr += 'b1_b2_conv1' 
                            elif style_layers==['block1_conv1']:
                                labelstr += 'b1_conv1' 
                            else:
                                labelstr += '_'+ numeral_layers_index_bitsVersion(style_layers)
                        else:
                            labelstr += '_'+ numeral_layers_index(style_layers)
                    plt.plot([19],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
                             marker=list_markers[fig_i_m],linestyle='')
                    fig_i += 1
                    
            title = optimizer + ' ' + transformOnFinalLayer + ' ' + metricploted + ' ' + final_clf
            plt.ion()
            plt.xlabel('Number of layers retrained')
            plt.ylabel(metricploted+' ArtUK')
            plt.title(title)
            plt.legend(loc='best')
            output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',target_dataset,'fig')
            pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
            name_of_the_figure = 'Summary_'+str(scenario)+'_'+ target_dataset+'_'+final_clf+'_Unfreezed_'+ optimizer+'_'+transformOnFinalLayer+'.png'
            if short:
                name_of_the_figure = 'Short_'+name_of_the_figure
            fname = os.path.join(output_path,name_of_the_figure)
            
            ### This does not work : need to be debug
    #         constrNet = 'VGGBaseNormCoherentAdaIn'
    #         number_im_considered = 10000
    #         style_layers_tab_VGGAdaIn = [['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
    #                                                     'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
    #                                                     'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
    #                                                     'block5_conv1','block5_conv2','block5_conv3','block5_conv4'],
    #                                                     ['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
    #                                                     ['block1_conv1','block2_conv1'],['block2_conv1'],['block1_conv1']]
       
    #         for style_layers in style_layers_tab_VGGAdaIn:
    # #            print(constrNet,style_layers)
    #             metrics = learn_and_eval(target_dataset,constrNet=constrNet,kind_method='FT',\
    #                                       epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
    #                                       forLatex=True,optimizer=optimizer,\
    #                                       opt_option=[opt_option[-1]],cropCenter=cropCenter,\
    #                                       style_layers=style_layers,getBeforeReLU=getBeforeReLU,\
    #                                       final_clf=final_clf,features='block5_pool',return_best_model=return_best_model,\
    #                                       onlyReturnResult=onlyPlot,number_im_considered=number_im_considered,\
    #                                       dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
    #                                       nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                
    #             if metrics is None:
    #                 continue
                
    #             metricI_per_class = metrics[metricploted_index]
    #             mMetric = np.mean(metricI_per_class)
    #             if fig_i in color_number_for_frozen:
    #                 fig_i_c = fig_i +1 
    #                 fig_i_m = fig_i
    #                 fig_i += 1
    #             else:
    #                 fig_i_c = fig_i
    #                 fig_i_m = fig_i
    #             labelstr = constrNet 
    #             if not(constrNet=='VGG'):
    #                 if BV:
    #                     if style_layers==['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
    #                                                     'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
    #                                                     'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
    #                                                     'block5_conv1','block5_conv2','block5_conv3','block5_conv4']:
                            
    #                         labelstr += '_all'
    #                     elif style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
    #                         labelstr += '*conv1' 
    #                     elif style_layers==['block1_conv1','block2_conv1']:
    #                         labelstr += 'b1_b2_conv1' 
    #                     elif style_layers==['block1_conv1']:
    #                         labelstr += 'b1_conv1' 
    #                     else:
    #                         labelstr += '_'+ numeral_layers_index_bitsVersion(style_layers)
    #                 else:
    #                     labelstr += '_'+ numeral_layers_index(style_layers)
    #             plt.plot([0],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
    #                      marker=list_markers[fig_i_m],linestyle='')
    #             fig_i += 1
            
            
    plt.show() 
    plt.pause(0.001)
#        input('Press to close')
    plt.savefig(fname)
#        plt.close()

def testForMovingStatsVisualisation():
    
    style_layers = ['bn_conv1']
    dropout=None
    regulOnNewLayer=None
    nesterov=False
    SGDmomentum=0.0
    decay=0.0
    target_dataset = 'Paintings'
    onlyPlot=False
    cropCenter=True
    BV=True
    final_clf = 'MLP2'
    epochs = 20
    optimizer = 'SGD'
    opt_option = [10**(-2)]
    return_best_model = True
    batch_size = 16 
    features = 'activation_48'
    freezingType = 'FromTop'
    transformOnFinalLayer = 'GlobalAveragePooling2D'
    pretrainingModif = 106
    network = 'ResNet50'
    #network = 'ResNet50_ROWD_CUMUL'
    metrics = learn_and_eval(target_dataset=target_dataset,constrNet=network,\
                         kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                         pretrainingModif=pretrainingModif,freezingType=freezingType,\
                         optimizer=optimizer,opt_option=opt_option,batch_size=batch_size\
                         ,final_clf=final_clf,features=features,return_best_model=return_best_model,\
                         onlyReturnResult=onlyPlot,style_layers=style_layers,
                         cropCenter=cropCenter,dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                         nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay,ReDo=True,verbose=True)
        
def PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'Paintings',scenario=0,
                              onlyPlot=False,cropCenter=True,BV=True):
    """
    Plot some mAP  on ArtUK Paintings dataset with different model just to see
    if we can say someting
    """
    
    network = 'ResNet50'
    # Normally metric = AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class but sometimes F1 is missing
    if metricploted=='mAP':
        metricploted_index = 0
    elif metricploted=='Precision':
        metricploted_index = 1
    elif metricploted=='Recall':
        metricploted_index = 2
    else:
        print(metricploted,' is unknown')
        raise(NotImplementedError)
        
    list_markers = ['o','s','X','*','v','^','<','>','d','1','2','3','4','8','h','H','p','d','$f$','P']
    # Les 3 frozen : 'o','s','X'
    # VGG : '*'
    
    NUM_COLORS = 20
    #color_number_for_frozen = [0,NUM_COLORS//2,NUM_COLORS-1]
    color_number_for_frozen = [0,NUM_COLORS//5,2*NUM_COLORS//5,3*NUM_COLORS//5,4*NUM_COLORS//5,NUM_COLORS-1]
    cm = plt.get_cmap('gist_rainbow')
    cNorm  = colors.Normalize(vmin=0, vmax=NUM_COLORS-1)
    scalarMap = mplcm.ScalarMappable(norm=cNorm, cmap=cm)
    list_freezingType = ['FromTop','FromBottom','Alter']
    #list_freezingType = ['FromTop']
    
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D'] # Not the flatten case for the moment
    #transformOnFinalLayer_tab = ['GlobalMaxPooling2D'] # Not the flatten case for the moment
    style_layers = ['bn_conv1']
    dropout=None
    regulOnNewLayer=None
    nesterov=False
    SGDmomentum=0.0
    decay=0.0
    if scenario==0:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD','adam']
        opt_option_tab = [[0.1,0.001],[0.01]] # Soit 0=10**-3
        return_best_model = False
    elif scenario==1:
        final_clf = 'MLP1'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
    elif scenario==2:
        final_clf = 'MLP1'
        epochs = 100
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-5)]]
        return_best_model = True
        # Really small learning rate 10**(-5)
    elif scenario==3:
        final_clf = 'MLP1'
        epochs = 5
        optimizer_tab = ['adam']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
    elif scenario==4:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
    elif scenario==5:
        final_clf = 'MLP1'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,0.01]] # WILDACT
        return_best_model = True
        # In WILDCAT we have lrp = 0.1, lp = 0.01 loss = MultiLabelSoftMarginLoss, Net = ResNet101
        # MultiLabelSoftMarginLoss seems to be the use of sigmoid on the outpur of the model and then the sum over classes of the binary cross entropy loss
    elif scenario==6:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
        dropout=0.2
        regulOnNewLayer='l2'
        nesterov=True
        SGDmomentum=0.99
        decay=0.0005
    elif scenario==7:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-3)]]
        return_best_model = True
        dropout=0.5
        SGDmomentum=0.99
        decay=0.0005
    elif scenario==8:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[0.1,10**(-4)]]
        return_best_model = True
        dropout=0.5
        SGDmomentum=0.9
    elif scenario==9:
        final_clf = 'MLP2'
        epochs = 20
        optimizer_tab = ['SGD']
        opt_option_tab = [[10**(-2)]]
        return_best_model = True
    else:
        # In Recognizing Characters in Art History Using Deep Learning  -  Madhu 2019 ?
        raise(NotImplementedError)


    range_l = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102,106] # For Resnet50
    batch_size = 16 
    features = 'activation_48'
    
    for optimizer,opt_option in zip(optimizer_tab,opt_option_tab): 
        for transformOnFinalLayer in transformOnFinalLayer_tab:
            j = 0
            fig_i = 0
            if len(opt_option)==1:
                opt_option_tab2 = [opt_option,[0.1,opt_option[0]]]
                opt_option_tab2 = [opt_option]
            else:
                opt_option_tab2 = [opt_option]
            plt.figure()
            list_perf = []
            for jj, opt_option2 in enumerate(opt_option_tab2):
                
                # Plot the value with a certain number of freeze or unfreeze layer
                for freezingType in list_freezingType:
                    list_perf += [[]]  
                    for pretrainingModif in range_l:
                        print('===',transformOnFinalLayer,freezingType,pretrainingModif,'opt_option :',opt_option2)
                        metrics = learn_and_eval(target_dataset=target_dataset,constrNet=network,\
                                                 kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                                 pretrainingModif=pretrainingModif,freezingType=freezingType,\
                                                 optimizer=optimizer,opt_option=opt_option2,batch_size=batch_size\
                                                 ,final_clf=final_clf,features=features,return_best_model=return_best_model,\
                                                 onlyReturnResult=onlyPlot,style_layers=style_layers,
                                                 cropCenter=cropCenter,dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                                 nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                                                # il faudra checker cela avec le ResNet 
            
                        if metrics is None:
                            continue
                        metricI_per_class = metrics[metricploted_index]
                        list_perf[j] += [np.mean(metricI_per_class)]
                        
                    if not(len(list(range_l))==len(list_perf[j])):
                        layers_j = list(range_l)[0:len(list_perf[j])]
                    else:
                        layers_j = list(range_l)
                        
                    labelstr = freezingType
                    if jj == 1:
                        labelstr += ' lrp 0.1'
                        
                    plt.plot(layers_j,list_perf[j],label=labelstr,color=scalarMap.to_rgba(color_number_for_frozen[fig_i]),\
                             marker=list_markers[fig_i],linestyle=':')
                    fig_i += 1
                    j += 1
    
            
        ## TODO il va falloir gerer les optimizers la !
    #        # Plot other proposed solution
            
    #        net_tab = ['VGG','VGGInNorm','VGGInNormAdapt','VGGBaseNorm','VGGBaseNormCoherent']
            
    #        
    #        # Case of the fine tuning with batch normalization 
            constrNet = 'ResNet50AdaIn'
            getBeforeReLU = True
            style_layers_tab_ResNet50AdaIn = [['bn_conv1'],['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],
                                         getBNlayersResNet50()]
            for style_layers in style_layers_tab_ResNet50AdaIn:
    #            print(constrNet,style_layers)
                metrics = learn_and_eval(target_dataset=target_dataset,constrNet=constrNet,\
                                         kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                         pretrainingModif=pretrainingModif,freezingType=freezingType,\
                                         optimizer=optimizer,opt_option=opt_option,batch_size=batch_size\
                                         ,final_clf=final_clf,features=features,return_best_model=return_best_model,\
                                         onlyReturnResult=onlyPlot,style_layers=style_layers,
                                         cropCenter=cropCenter,dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                         nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                if metrics is None:
                    continue
                metricI_per_class = metrics[metricploted_index]
                mMetric = np.mean(metricI_per_class)
                if fig_i in color_number_for_frozen:
                    fig_i_c = fig_i +1 
                    fig_i_m = fig_i
                    fig_i += 1
                else:
                    fig_i_c = fig_i
                    fig_i_m = fig_i
                labelstr = constrNet 
                if not(constrNet=='VGG' or constrNet=='ResNet50'):
                    if BV:
                        if getResNetLayersNumeral_bitsVersion(style_layers) == getResNetLayersNumeral_bitsVersion(getBNlayersResNet50()):
                            labelstr += '_all'
                        elif style_layers == ['bn_conv1']:
                            labelstr += '_bnc1'
                        elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                            labelstr += '_bn_*1'
                        else:
                            labelstr += '_'+  getResNetLayersNumeral_bitsVersion(style_layers)
                    else:
                        if getResNetLayersNumeral(style_layers) == getResNetLayersNumeral(getBNlayersResNet50()):
                            labelstr += '_all'
                        elif style_layers == ['bn_conv1']:
                            labelstr += '_bnc1'
                        elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                            labelstr += '_bn_*1'
                        else:
                            labelstr += '_'+  getResNetLayersNumeral(style_layers)
                x = len(style_layers)
                plt.plot([x],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
                         marker=list_markers[fig_i_m],linestyle='')
                fig_i += 1
    #            
            
            # Case BNRF
            net_tab = ['ResNet50_BNRF','ResNet50_ROWD_CUMUL','ResNet50_ROWD_CUMUL_AdaIn']
            net_tab = ['ResNet50_ROWD_CUMUL','ResNet50_ROWD_CUMUL_AdaIn']
            style_layers_tab_forOther = [[]] # TODO il faudra changer cela a terme
            style_layers_tab_forResNet50_ROWD = [['bn_conv1'],['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],
                                         getBNlayersResNet50()]
            number_im_considered = 10000
            final_clf = 'MLP2'
            source_dataset = 'ImageNet'
            kind_method = 'FT'
            normalisation = False
            getBeforeReLU = True
            forLatex = True

            for constrNet in net_tab:
                print('~~~ ',constrNet,' ~~~')
                if constrNet=='ResNet50_ROWD_CUMUL' or constrNet=='ResNet50_ROWD_CUMUL_AdaIn':
                    style_layers_tab = style_layers_tab_forResNet50_ROWD
                elif constrNet=='ResNet50' or constrNet=='ResNet50_BNRF':
                    style_layers_tab = [[]]
                else:
                    style_layers_tab = style_layers_tab_forOther
                for style_layers in style_layers_tab:
                    labelstr = constrNet 
                    if not(constrNet=='ResNet50' or constrNet=='ResNet50_BNRF'):
                        if BV:
                            if getResNetLayersNumeral_bitsVersion(style_layers) == getResNetLayersNumeral_bitsVersion(getBNlayersResNet50()):
                                labelstr += '_all'
                            elif style_layers == ['bn_conv1']:
                                labelstr += '_bnc1'
                            elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                                labelstr += '_bn_*1'
                            else:
                                labelstr += '_'+ getResNetLayersNumeral_bitsVersion(style_layers)

                        else:
                            labelstr += '_'+ getResNetLayersNumeral(style_layers)
                    metrics = learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                       constrNet,kind_method,style_layers,gridSearch=False,
                                       number_im_considered=number_im_considered,
                                       normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
                                       transformOnFinalLayer=transformOnFinalLayer,\
                                       optimizer=optimizer,opt_option=opt_option,batch_size=batch_size\
                                       ,return_best_model=return_best_model,\
                                       forLatex=forLatex,cropCenter=cropCenter,\
                                       momentum=0.9,batch_size_RF=16,epochs_RF=20,\
                                       onlyReturnResult=onlyPlot,verbose=True,\
                                       dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                       nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                    if metrics is None:
                        continue
                    metricI_per_class = metrics[metricploted_index]
                    mMetric = np.mean(metricI_per_class)
                    if fig_i in color_number_for_frozen:
                        fig_i_c = fig_i +1 
                        fig_i_m = fig_i
                        fig_i += 1
                    else:
                        fig_i_c = fig_i
                        fig_i_m = fig_i
                    x = 0 
                    if constrNet=='ResNet50_ROWD_CUMUL' or constrNet=='ResNet50_BNRF':
                        x = 106
                    elif constrNet=='ResNet50_ROWD_CUMUL_AdaIn':
                        x = len(style_layers)
                    plt.plot([x],[mMetric],label=labelstr,color=scalarMap.to_rgba(fig_i_c),\
                             marker=list_markers[fig_i_m],linestyle='')
                    fig_i += 1
            
            
            # At the end
            
            optstr  = ''        
            for o in opt_option:     
                optstr += ' ' +str(o)
            optstr += ' ' +str(epochs)
            optstr_ = optstr.replace(' ','_')
            title = optimizer+ optstr + ' ' + transformOnFinalLayer + ' ' +final_clf + ' ' + metricploted
            plt.ion()
            plt.xlabel('Number of layers retrained')
            if target_dataset=='Paintings':
                target_dataset_str = 'ArtUK'
            else:
                target_dataset_str  = target_dataset
            plt.ylabel(metricploted+' '+target_dataset_str)
            plt.title(title)
            plt.legend(loc='best')
            output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',target_dataset,'fig')
            pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
            name_of_the_figure = 'Summary_'+str(scenario)+'_'+ target_dataset+network+'_Unfreezed_'+\
                optimizer+optstr_+'_'+transformOnFinalLayer+final_clf+target_dataset_str
            if cropCenter:
                name_of_the_figure += '_CropCenter'   
            name_of_the_figure+='.png'
            fname = os.path.join(output_path,name_of_the_figure)
            plt.show() 
            plt.pause(0.001)
            
            
            
            plt.savefig(fname)
            
def PlotSomePerformanceResNet_V2(metricploted='mAP',target_dataset = 'Paintings',
                              onlyPlot=False,cropCenter=True,BV=True):
    """
    Plot some mAP  on ArtUK Paintings dataset with different model just to see
    if we can say someting 
    
    But we will focus on the fact of unfreezing some part of the network even when we use 
    ResNet_ROWD as initialisation of the model
    """
    
    
    # Normally metric = AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class but sometimes F1 is missing
    if metricploted=='mAP':
        metricploted_index = 0
    elif metricploted=='Precision':
        metricploted_index = 1
    elif metricploted=='Recall':
        metricploted_index = 2
    else:
        print(metricploted,' is unknown')
        raise(NotImplementedError)
        
    list_markers = ['o','s','X','*','v','^','<','>','d','1','2','3','4','8','h','H','p','d','$f$','P']
    # Les 3 frozen : 'o','s','X'
    # VGG : '*'
    
    NUM_COLORS = 20
    #color_number_for_frozen = [0,NUM_COLORS//2,NUM_COLORS-1]
    #color_number_for_frozen = [0,NUM_COLORS//5,2*NUM_COLORS//5,3*NUM_COLORS//5,4*NUM_COLORS//5,NUM_COLORS-1]
    color_number_for_frozen = []
    cm = plt.get_cmap('gist_rainbow')
    cNorm  = colors.Normalize(vmin=0, vmax=NUM_COLORS-1)
    scalarMap = mplcm.ScalarMappable(norm=cNorm, cmap=cm)
    list_freezingType = ['FromTop','FromBottom','Alter']
    list_freezingType = ['FromTop']
    
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D'] # Not the flatten case for the moment
    transformOnFinalLayer_tab = ['GlobalAveragePooling2D'] # Not the flatten case for the moment
    #transformOnFinalLayer_tab = ['GlobalMaxPooling2D'] # Not the flatten case for the moment
    style_layers = ['bn_conv1']
    dropout=None
    regulOnNewLayer=None
    nesterov=False
    SGDmomentum=0.0
    decay=0.0
    
    print("Attention les histoires de scenario ne serve a rien ici !!! ")

    range_l = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96, 102,106] # For Resnet50
    batch_size = 16 
    features = 'activation_48'
    
    final_clf = 'MLP2'
    
    return_best_model = True
    opt_option_tab = [[10**(-2)],[0.1,10**(-2)],[10**(-3)],[0.1,10**(-3)]]
    epochs_tab = [20,20,200,200]
    optimizer = 'SGD'
    
    # ResNetCase
    for transformOnFinalLayer in transformOnFinalLayer_tab:
        plt.figure()
        fig_i = 0
        list_perf = []
        j = 0
        for opt_option,epochs in zip(opt_option_tab,epochs_tab): 
    
            network = 'ResNet50'
            # Plot the value with a certain number of freeze or unfreeze layer
            for freezingType in list_freezingType:
                list_perf += [[]]  
                for pretrainingModif in range_l:
                    #print('===',transformOnFinalLayer,freezingType,pretrainingModif,'opt_option :',opt_option)
                    metrics = learn_and_eval(target_dataset=target_dataset,constrNet=network,\
                                             kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                             pretrainingModif=pretrainingModif,freezingType=freezingType,\
                                             optimizer=optimizer,opt_option=opt_option,batch_size=batch_size\
                                             ,final_clf=final_clf,features=features,return_best_model=return_best_model,\
                                             onlyReturnResult=onlyPlot,style_layers=style_layers,
                                             cropCenter=cropCenter,dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                             nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)
                                            # il faudra checker cela avec le ResNet 
        
                    if metrics is None:
                        continue
                    metricI_per_class = metrics[metricploted_index]
                    list_perf[j] += [np.mean(metricI_per_class)]
                    
                if not(len(list(range_l))==len(list_perf[j])):
                    layers_j = list(range_l)[0:len(list_perf[j])]
                else:
                    layers_j = list(range_l)
                    
                labelstr = freezingType
                if len(opt_option)==2:
                    labelstr += ' lrp '+str(opt_option[0])
                labelstr += ' lr '+str(opt_option[-1])
                labelstr += ' e '+str(epochs)
                    
                plt.plot(layers_j,list_perf[j],label=labelstr,color=scalarMap.to_rgba(fig_i),\
                         marker=list_markers[fig_i],linestyle=':')
                fig_i += 1
                j += 1
                    
            # ResNet50_ROWD_CUMUL as initialisation 
            style_layers_tab_forResNet50_ROWD = [['bn_conv1'],['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],
                                          getBNlayersResNet50()]
            constrNet = 'ResNet50_ROWD_CUMUL'

            # Plot the value with a certain number of freeze or unfreeze layer
            for freezingType in list_freezingType:
                for style_layers in style_layers_tab_forResNet50_ROWD:
#            print(constrNet,style_layers)
                    list_perf += [[]]
                    for pretrainingModif in range_l:
                        print(constrNet,pretrainingModif)
                        metrics = learn_and_eval(target_dataset=target_dataset,constrNet=constrNet,\
                                          kind_method='FT',epochs=epochs,transformOnFinalLayer=transformOnFinalLayer,\
                                          pretrainingModif=pretrainingModif,freezingType=freezingType,\
                                          optimizer=optimizer,opt_option=opt_option,batch_size=batch_size\
                                          ,final_clf=final_clf,features=features,return_best_model=return_best_model,\
                                          onlyReturnResult=onlyPlot,style_layers=style_layers,
                                          cropCenter=cropCenter,dropout=dropout,regulOnNewLayer=regulOnNewLayer,\
                                          nesterov=nesterov,SGDmomentum=SGDmomentum,decay=decay)                                                # il faudra checker cela avec le ResNet 
                        print(metrics)
                        if metrics is None:
                            continue
                        metricI_per_class = metrics[metricploted_index]
                        list_perf[j] += [np.mean(metricI_per_class)]
                    
                    if not(len(list(range_l))==len(list_perf[j])):
                        layers_j = list(range_l)[0:len(list_perf[j])]
                    else:
                        layers_j = list(range_l)
                        
                    labelstr = freezingType
                    if len(opt_option)==2:
                        labelstr += ' lrp '+str(opt_option[0])
                    labelstr += ' lr '+str(opt_option[-1])
                    labelstr += ' e '+str(epochs)
                    if BV:
                        if getResNetLayersNumeral_bitsVersion(style_layers) == getResNetLayersNumeral_bitsVersion(getBNlayersResNet50()):
                            labelstr += '_all'
                        elif style_layers == ['bn_conv1']:
                            labelstr += '_bnc1'
                        elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                            labelstr += '_bn_*1'
                        else:
                            labelstr += '_'+  getResNetLayersNumeral_bitsVersion(style_layers)
                    else:
                        if getResNetLayersNumeral(style_layers) == getResNetLayersNumeral(getBNlayersResNet50()):
                            labelstr += '_all'
                        elif style_layers == ['bn_conv1']:
                            labelstr += '_bnc1'
                        elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                            labelstr += '_bn_*1'
                        else:
                            labelstr += '_'+  getResNetLayersNumeral(style_layers)
                        
                            
                        plt.plot(layers_j,list_perf[j],label=labelstr,color=scalarMap.to_rgba(fig_i),\
                             marker=list_markers[fig_i],linestyle=':')
                        fig_i += 1
                        j += 1
    
        title = optimizer + ' ' + transformOnFinalLayer + ' ' +final_clf + ' ' + metricploted
        plt.ion()
        plt.xlabel('Number of layers retrained')
        if target_dataset=='Paintings':
            target_dataset_str = 'ArtUK'
        else:
            target_dataset_str  = target_dataset
        plt.ylabel(metricploted+' '+target_dataset_str)
        plt.title(title)
        plt.legend(loc='best')
        output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',target_dataset,'fig')
        pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
        name_of_the_figure = 'Summary_CompInitalisation_'+ target_dataset+network+'_Unfreezed_DiffModels_'+\
            optimizer+'_'+transformOnFinalLayer+final_clf+target_dataset_str
        if cropCenter:
            name_of_the_figure += '_CropCenter'   
        name_of_the_figure+='.png'
        fname = os.path.join(output_path,name_of_the_figure)
        plt.show() 
        plt.pause(0.001)

        plt.savefig(fname)

                    
def RunEval_MLP_onConvBlock():
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D','']
    for optimizer,opt_option in zip(['adam','SGD'],[[0.01],[0.01]]):
        for transformOnFinalLayer in transformOnFinalLayer_tab:
            if transformOnFinalLayer=='':
                feature='flatten'
            else:
                feature='block5_pool'
            metrics = learn_and_eval(target_dataset='Paintings',constrNet='VGG',features=feature,\
                                     kind_method='TL',epochs=20,transformOnFinalLayer=transformOnFinalLayer,\
                                     optimizer=optimizer,opt_option=opt_option,final_clf='MLP2')
    
def RunAllEvaluation(target_dataset='Paintings',forLatex=False):
    source_dataset = 'ImageNet'
    ## Run the baseline
    
    transformOnFinalLayer_tab = ['GlobalMaxPooling2D','GlobalAveragePooling2D']
    for normalisation in [False]:
        final_clf_list = ['MLP2','LinearSVC'] # LinearSVC but also MLP
        features_list = ['fc2','fc1','flatten'] # We want to do fc2, fc1, max spatial and concat max and min spatial
        features_list = [] # We want to do fc2, fc1, max spatial and concat max and min spatial
         # We want to do fc2, fc1, max spatial and concat max and min spatial
        # Normalisation and not normalise
        kind_method = 'TL'
        style_layers = []
        
        # Baseline with just VGG
        constrNet = 'VGG'
        for final_clf in final_clf_list:
            for features in features_list:
                learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                           constrNet,kind_method,style_layers,gridSearch=False,
                           normalisation=normalisation,transformOnFinalLayer='')
            
            # Pooling on last conv block
            for transformOnFinalLayer in transformOnFinalLayer_tab:
                features = 'block5_pool'
                learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                           constrNet,kind_method,style_layers,gridSearch=False,
                           normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,\
                           forLatex=forLatex)
         
        # With VGGInNorm
        style_layers_tab_forOther = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                         ['block1_conv1','block2_conv1'],['block1_conv1']]
        style_layers_tab_foVGGBaseNormCoherentr = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                         ['block1_conv1','block2_conv1']]
        
        features_list = ['fc2','fc1','flatten']
        features_list = ['fc2','fc1']
        features_list = []
        net_tab = ['VGGInNorm','VGGInNormAdapt','VGGBaseNorm','VGGBaseNormCoherent']
        number_im_considered_tab = [1000]
        for getBeforeReLU in [True,False]:
            for constrNet in net_tab:
                if constrNet=='VGGBaseNormCoherent':
                    style_layers_tab = style_layers_tab_foVGGBaseNormCoherentr
                else:
                    style_layers_tab = style_layers_tab_forOther
                for final_clf in final_clf_list:
                    for style_layers in style_layers_tab:
                        for features in features_list:
                            for number_im_considered in number_im_considered_tab:
                                if not(forLatex): print('=== getBeforeReLU',getBeforeReLU,'constrNet',constrNet,'final_clf',final_clf,'features',features,'number_im_considered',number_im_considered,'style_layers',style_layers)
                                learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                       constrNet,kind_method,style_layers,gridSearch=False,
                                       number_im_considered=number_im_considered,\
                                       normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
                                       forLatex=forLatex)
                       
                        number_im_considered = 1000
                        # Pooling on last conv block
                        for transformOnFinalLayer in transformOnFinalLayer_tab:
                            if not(forLatex):  print('=== getBeforeReLU',getBeforeReLU,'constrNet',constrNet,'final_clf',final_clf,'features',features,'number_im_considered',number_im_considered,'style_layers',style_layers,'transformOnFinalLayer',transformOnFinalLayer)
                            features = 'block5_pool'
                            learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                       constrNet,kind_method,style_layers,gridSearch=False,
                                       number_im_considered=number_im_considered,
                                       normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
                                       transformOnFinalLayer=transformOnFinalLayer,\
                                       forLatex=forLatex)
                            
def RunAllEvaluation_ForFeatureExtractionModel(forLatex=False,printForTabularLatex=False):
    """
    Le but de cette fonction est de faire les calculs avec les differentes methodes 
    et voir ce que cela donne dans le cadre de l'extraction de features
    """
    verbose = True
    if printForTabularLatex:
        forLatex = False
        verbose=False
    
    metricploted = 'mAP'
    if metricploted=='mAP':
        metricploted_index = 0
    elif metricploted=='Precision':
        metricploted_index = 1
    elif metricploted=='Recall':
        metricploted_index = 2
    else:
        print(metricploted,' is unknown')
        raise(NotImplementedError)
    
    source_dataset = 'ImageNet'
    normalisation = False
    kind_method = 'TL'

    
    final_clf_list = ['LinearSVC','MLP2','MLP2bis'] # LinearSVC but also MLP : pas encore fini
    gridSearchTab =[True,False,False] # LinearSVC but also MLP : pas encore fini
    #gridSearchTab =[False] # LinearSVC but also MLP : pas encore fini
    #final_clf_list = ['LinearSVC'] # LinearSVC but also MLP
    
    dataset_tab = ['Paintings','IconArt_v1']
    #dataset_tab = ['Paintings']
    
    for target_dataset in dataset_tab:
        print('===',target_dataset,'===')
        
        # VGG case 
        for features,transformOnFinalLayer in zip(['fc2','block5_pool','block5_pool'],['','GlobalMaxPooling2D','GlobalAveragePooling2D']):
            
            if printForTabularLatex:
                str_print_base = '& '
                if features=='block5_pool':
                   str_print_base += 'b5p'
                else:
                   str_print_base +=  features
                if transformOnFinalLayer=='GlobalMaxPooling2D':
                   str_print_base += ' Max' 
                if transformOnFinalLayer=='GlobalAveragePooling2D':
                   str_print_base += ' Avg' 
            else:
                print(features,transformOnFinalLayer)
                  
            constrNet = 'VGG'
            if printForTabularLatex: str_print = constrNet + str_print_base + '& Feature extraction & •'
            for final_clf,gridSearch in zip(final_clf_list,gridSearchTab): 
                if not(printForTabularLatex): 
                    print('==',final_clf,'==')

                # Baseline Case
                
                if final_clf=='LinearSVC':
                    metrics = learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                  constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                  normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                  ReDo=False)
                elif final_clf=='MLP2':
                    metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                  constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                  normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                  dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-3)],\
                                  epochs=20,nesterov=True,SGDmomentum=0.99,decay=0.0005,ReDo=False)
                elif final_clf=='MLP2bis':
                    metrics =learn_and_eval(target_dataset,source_dataset,'MLP2',features,\
                                  constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                  normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                  optimizer='SGD',opt_option=[10**(-2)],\
                                  epochs=20,SGDmomentum=0.9,decay=10**(-4),ReDo=False)
                        
                
                if printForTabularLatex:
                    metricI_per_class = metrics[metricploted_index]
                    mMetric = np.mean(metricI_per_class)
                    str_print += '& {0:.2f}'.format(100*mMetric)
                    
            if printForTabularLatex: print(str_print.replace('_','\_')+'\\\\')
                
            # Statistics model
            net_tab = ['VGGInNorm','VGGInNormAdapt','VGGBaseNorm','VGGBaseNormCoherent']
            style_layers_tab_forOther = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                        ['block1_conv1','block2_conv1'],['block1_conv1']]
            style_layers_tab_foVGGBaseNormCoherentr = [['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1'],
                        ['block1_conv1','block2_conv1']]
            number_im_considered = 10000
            getBeforeReLU = True
    
            for constrNet in net_tab:
                

                
                if constrNet=='VGGBaseNormCoherent':
                    style_layers_tab = style_layers_tab_foVGGBaseNormCoherentr
                else:
                    style_layers_tab = style_layers_tab_forOther
                for style_layers in style_layers_tab:
                    if printForTabularLatex: 
                        str_print = '' + str_print_base + '& ' +constrNet +' &'
                        if style_layers==['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
                                                        'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
                                                        'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
                                                        'block5_conv1','block5_conv2','block5_conv3','block5_conv4']:
                            
                            str_print += 'all'
                        elif style_layers==['block1_conv1','block2_conv1','block3_conv1','block4_conv1', 'block5_conv1']:
                            str_print += '*conv1' 
                        elif style_layers==['block1_conv1','block2_conv1']:
                            str_print += 'b1_b2_conv1' 
                        elif style_layers==['block1_conv1']:
                            str_print += 'b1_conv1'
                        
                    for final_clf,gridSearch in zip(final_clf_list,gridSearchTab): 
                        if not(printForTabularLatex): 
                            print('==',final_clf,'==')
                        
                        if not(forLatex): 
                            if not(printForTabularLatex):
                                print('--- getBeforeReLU',getBeforeReLU,'constrNet',constrNet,'final_clf',final_clf,\
                              'features',features,'transformOnFinalLayer',transformOnFinalLayer,'number_im_considered',number_im_considered,'style_layers',style_layers)
                        if final_clf=='LinearSVC':
                            metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                  constrNet,kind_method,style_layers,gridSearch=gridSearch,
                                  number_im_considered=number_im_considered,\
                                  normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
                                  forLatex=forLatex,transformOnFinalLayer=transformOnFinalLayer,
                                  ReDo=False)
                        elif final_clf=='MLP2':
                            metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                  constrNet,kind_method,style_layers,gridSearch=gridSearch,
                                  number_im_considered=number_im_considered,\
                                  normalisation=normalisation,getBeforeReLU=getBeforeReLU,\
                                  forLatex=forLatex,transformOnFinalLayer=transformOnFinalLayer,
                                  dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-3)],\
                                  epochs=20,nesterov=True,SGDmomentum=0.99,decay=0.0005,ReDo=False)
                        elif final_clf=='MLP2bis':
                            metrics =learn_and_eval(target_dataset,source_dataset,'MLP2',features,\
                                          constrNet,kind_method,style_layers=style_layers,gridSearch=gridSearch,
                                          normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                          optimizer='SGD',opt_option=[10**(-2)],\
                                          epochs=20,SGDmomentum=0.9,decay=10**(-4),ReDo=False)
                                
                        if printForTabularLatex:
                            metricI_per_class = metrics[metricploted_index]
                            mMetric = np.mean(metricI_per_class)
                            str_print += '& {0:.2f}'.format(100*mMetric)
                            
                    if printForTabularLatex: print(str_print.replace('_','\_')+'\\\\')
                                
            
#            # ResNet50 case
        for features,transformOnFinalLayer in zip(['activation_48','activation_48'],['GlobalMaxPooling2D','GlobalAveragePooling2D']):
            
            # Baseline Case
            constrNet = 'ResNet50'
            
            if printForTabularLatex:
                str_print_base = '& '
                if features=='activation_48':
                   str_print_base += 'ac48p'
                if transformOnFinalLayer=='GlobalMaxPooling2D':
                   str_print_base += ' Max' 
                if transformOnFinalLayer=='GlobalAveragePooling2D':
                   str_print_base += ' Avg' 
            else:
               print(features,transformOnFinalLayer) 
                  
            str_print = constrNet + str_print_base + '& Feature extraction & •'
            for final_clf,gridSearch in zip(final_clf_list,gridSearchTab): 
                if not(printForTabularLatex): 
                    print('==',final_clf,'==')
                if final_clf=='LinearSVC':
                    metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                   constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                   normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                   ReDo=False)
                elif final_clf=='MLP2':
                    metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                   constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                   normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                   dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-43)],\
                                   epochs=20,nesterov=True,SGDmomentum=0.99,decay=0.0005,ReDo=False)
                elif final_clf=='MLP2bis':
                    metrics =learn_and_eval(target_dataset,source_dataset,'MLP2',features,\
                                   constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
                                   normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                   optimizer='SGD',opt_option=[10**(-2)],\
                                   epochs=20,SGDmomentum=0.9,decay=10**(-4),ReDo=False)
                        
                if printForTabularLatex:
                    metricI_per_class = metrics[metricploted_index]
                    mMetric = np.mean(metricI_per_class)
                    str_print += '& {0:.2f}'.format(100*mMetric)
                    
            if printForTabularLatex: print(str_print.replace('_','\_')+'\\\\')
            
            # Statistics model
            style_layers_tab_forResNet50_ROWD = [['bn_conv1'],['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],
                                         getBNlayersResNet50()]
            
            constrNet = 'ResNet50_ROWD_CUMUL'
             
            for computeGlobalVariance in [False,True]:
                if not(printForTabularLatex): print('------ computeGlobalVariance = ',computeGlobalVariance,'------')
                
                for style_layers in style_layers_tab_forResNet50_ROWD:
                    if printForTabularLatex:
                        str_print = '' + str_print_base + '& ' +constrNet
                        if computeGlobalVariance:
                            str_print += 'GlobalVar'
                        str_print += '&'
                        
                        if getResNetLayersNumeral(style_layers) == getResNetLayersNumeral(getBNlayersResNet50()):
                            str_print += 'all'
                        elif style_layers == ['bn_conv1']:
                            str_print += 'bnc1'
                        elif style_layers == ['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1']:
                            str_print += 'bn_*1'
                    
                    for final_clf,gridSearch in zip(final_clf_list,gridSearchTab): 
                        if not(printForTabularLatex): 
                            print('==',final_clf,'==')
                    
                        if final_clf=='LinearSVC':
                            metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                       constrNet,kind_method,style_layers=style_layers,gridSearch=gridSearch,
                                       normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                       ReDo=False,computeGlobalVariance=computeGlobalVariance,verbose=verbose)
                        elif final_clf=='MLP2':
                            metrics =learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                                       constrNet,kind_method,style_layers=style_layers,gridSearch=gridSearch,
                                       normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                       dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-3)],\
                                       epochs=20,nesterov=True,SGDmomentum=0.99,decay=0.0005,ReDo=False,computeGlobalVariance=computeGlobalVariance)
                        elif final_clf=='MLP2bis':
                            metrics =learn_and_eval(target_dataset,source_dataset,'MLP2',features,\
                                   constrNet,kind_method,style_layers=style_layers,gridSearch=gridSearch,
                                   normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                                   optimizer='SGD',opt_option=[10**(-2)],\
                                   epochs=20,SGDmomentum=0.9,decay=10**(-4),ReDo=False)
                        if printForTabularLatex:
                            metricI_per_class = metrics[metricploted_index]
                            mMetric = np.mean(metricI_per_class)
                            str_print += '& {0:.2f}'.format(100*mMetric)
                            
                    if printForTabularLatex: print(str_print.replace('_','\_')+'\\\\')
                
            
            # constrNet = 'ResNet50_BNRF'
            # if final_clf=='LinearSVC':
            #     learn_and_eval(target_dataset,source_dataset,final_clf,features,\
            #                     constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
            #                     normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
            #                     batch_size_RF=16,epochs_RF=20,momentum=0.9,ReDo=False)
            # elif final_clf=='MLP2':
            #     learn_and_eval(target_dataset,source_dataset,final_clf,features,\
            #                     constrNet,kind_method,style_layers=[],gridSearch=gridSearch,
            #                     normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
            #                     batch_size_RF=16,epochs_RF=20,momentum=0.9,
            #                     dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-3)],\
            #                 epochs=20,nesterov=True,SGDmomentum=0.99,decay=0.0005,ReDo=False)
            # elif final_clf=='MLP2bis':
            #     learn_and_eval(target_dataset,source_dataset,'MLP2',features,\
            #             constrNet,kind_method,style_layers=style_layers,gridSearch=gridSearch,
            #             normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
            #             optimizer='SGD',opt_option=[10**(-2)],\
            #             epochs=20,SGDmomentum=0.9,decay=10**(-4),ReDo=False)
       

def RunAllEvaluation_FineTuningResNet(onlyPlot=False):
    """
    @param onlyPlot = True if you only want to plot the new values
    """
    
    dataset_tab = ['Paintings','IconArt_v1']
    #dataset_tab = ['Paintings']
    # a decommenter pour afficher les courbes
    scenario = 9
    for target_dataset in dataset_tab:
        PlotSomePerformanceResNet(target_dataset = target_dataset,scenario=scenario,
                              onlyPlot=onlyPlot,cropCenter=True,BV=True)
    
def RunAllEvaluation_FineTuningVGG(onlyPlot=False):
    """
    @param onlyPlot = True if you only want to plot the new values
    """   
    dataset_tab = ['Paintings','IconArt_v1']
    scenario=11
    for target_dataset in dataset_tab:
        PlotSomePerformanceVGG(target_dataset = target_dataset,
                           onlyPlot=onlyPlot,scenario=scenario,BV=True,cropCenter=True)
 
def TrucBizarre(target_dataset='Paintings'):
    # Ces deux manieres de faire devrait retourner les memes performances et ce n'est pas le cas....
    
    # Ici cas du transfert learning avec extraction de features puis entrainement d'un MLP2
    metrics = learn_and_eval(target_dataset=target_dataset,constrNet='VGG',pretrainingModif=False,\
                   kind_method='TL',epochs=1,transformOnFinalLayer='GlobalAveragePooling2D',\
                   final_clf='MLP2',forLatex=True,features='block5_pool',ReDo=True,plotConv=True,\
                   optimizer='adam')
    AP_TL = metrics[0]
    print('TL',AP_TL)
    
    # Ici fine-tuning du réseau mais avec l'ensemble du réseau pretained qui est freeze /
    # fixe / non trainable : on rajoute juste un MLP2 a la fin
    metrics2 = learn_and_eval(target_dataset=target_dataset,constrNet='VGG',pretrainingModif=False,\
                   kind_method='FT',epochs=1,transformOnFinalLayer='GlobalAveragePooling2D',\
                   final_clf='MLP2',forLatex=True,ReDo=True,plotConv=True,optimizer='adam')
    AP_FT = metrics2[0]
    print('FT',AP_FT)

def Test_Unfrozen_ResNet():
    print('=== From Top ===')
    metrics = learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',\
                         kind_method='FT',epochs=0,transformOnFinalLayer='GlobalMaxPooling2D',\
                         pretrainingModif=3,freezingType='FromTop',\
                         optimizer='adam',opt_option=[0.001],batch_size=16\
                         ,final_clf='MLP2',features='avg_pool',return_best_model=True,\
                         onlyReturnResult=False,style_layers=['bn_conv1'],verbose=True)
    
    
    print('=== From Bottom ===')
    metrics = learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',\
                         kind_method='FT',epochs=0,transformOnFinalLayer='GlobalMaxPooling2D',\
                         pretrainingModif=3,freezingType='FromBottom',\
                         optimizer='adam',opt_option=[0.001],batch_size=16\
                         ,final_clf='MLP2',features='avg_pool',return_best_model=True,\
                         onlyReturnResult=False,style_layers=['bn_conv1'],verbose=True)

def Test_Apropos_DuRebond():
    
    # il semblerait que dans certains cas on arrive a faire du 57% dans certains cas
    tab_AP =[]
    for i in range(3):
        AP_per_class,P_per_class,R_per_class,P20_per_class,F1_per_class\
        =learn_and_eval(target_dataset='IconArt_v1',final_clf='MLP2',\
                        kind_method='FT',epochs=20,ReDo=True,optimizer='SGD',\
                        opt_option=[0.1,0.001],features='block5_pool',\
                        batch_size=32,constrNet='VGG',freezingType='FromTop',\
                        pretrainingModif=3,plotConv=False)
        print(i,np.mean(AP_per_class))
        tab_AP += [np.mean(AP_per_class)]
 
def Crowley_reproduction_results():
    
    target_dataset = 'Paintings'
    ReDo = False
    
    print('The following experiments will normally reproduce the performance of Crowley 2016 with VGG central crop, grid search on C parameter of SVM but no augmentation of the image (multi crop).')
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='LinearSVC',features='fc2',\
                   constrNet='VGG',kind_method='TL',gridSearch=True,ReDo=ReDo,cropCenter=True)
    # 67.1 & 50.6 & 93.0 & 74.6 & 61.3 & 70.2 & 56.1 & 78.8 & 67.1 & 85.5 & 70.5 \\ 
    
    print('Same experiment with ResNet50 ')
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='LinearSVC',features='activation_48',\
                   transformOnFinalLayer='GlobalAveragePooling2D',
                   constrNet='ResNet50',kind_method='TL',gridSearch=True,ReDo=ReDo,cropCenter=True)
    # ResNet50 Block1-5\_conv1 activation\_48 GlobalAveragePooling2D LinearSVCGS 
    # & 71.1 & 48.3 & 92.9 & 75.8 & 64.4 & 72.5 & 56.6 & 80.7 & 70.5 & 88.5 & 72.2 \\ 
    
    print('Same experiment with ResNet50 but a MLP2')
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='activation_48',\
                   constrNet='ResNet50',kind_method='TL',gridSearch=False,ReDo=ReDo,\
                   transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True)
    # & 57.3 & 34.0 & 89.7 & 68.9 & 51.5 & 62.4 & 45.9 & 72.9 & 60.5 & 77.1 & 62.0 \\
    
    print('Same experiment with ResNet50 but a MLP3 with dropout etc')
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='activation_48',\
                   constrNet='ResNet50',kind_method='TL',gridSearch=False,ReDo=ReDo,\
                   transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
                   dropout=0.5,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-4)],\
                   epochs=50)
    # & 3.4 & 10.8 & 64.7 & 25.3 & 12.9 & 16.2 & 18.7 & 24.9 & 17.9 & 4.2 & 19.9 \\ 
    
    print('Same experiment with ResNet50 but a MLP3 with dropout decay etc')
    # 72.4 AP sur Paintings : a verifier car il y  avait de probleme avec le crop center fct
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='activation_48',\
                   constrNet='ResNet50',kind_method='TL',gridSearch=False,ReDo=ReDo,\
                   transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
                   dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[5*10**(-4)],\
                   epochs=50,nesterov=True,SGDmomentum=0.99,decay=0.0005)
    # & 71.4 & 49.3 & 93.3 & 76.5 & 63.8 & 73.2 & 60.1 & 82.0 & 69.3 & 85.5 & 72.4 \\    
    
    print('Same experiment with ResNet50 with a fine tuning of the whole model')
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='activation_48',\
                   constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=ReDo,\
                   transformOnFinalLayer='GlobalAveragePooling2D',pretrainingModif=True,\
                   optimizer='SGD',opt_option=[0.1,0.001],return_best_model=True,
                   epochs=20,cropCenter=True)   
    #& 13.8 & 9.9 & 42.5 & 32.3 & 16.1 & 23.2 & 16.8 & 30.6 & 20.5 & 10.6 & 21.6 \\
    
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='activation_48',\
               constrNet='ResNet50',kind_method='TL',gridSearch=False,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
               regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=50,return_best_model=True,SGDmomentum=0.99,dropout=0.2)
    # & 73.1 & 46.9 & 92.8 & 76.4 & 65.1 & 73.4 & 56.8 & 80.2 & 71.1 & 88.6 & 72.4 \\
    
    
def testResNet_FineTuning():
    """
    The goal of this function is tout 
    """
    target_dataset = 'Paintings'
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP1',features='block5_pool',\
           constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
           transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
           regulOnNewLayer=None,optimizer='RMSprop',opt_option=[0.001],\
           epochs=20,SGDmomentum=0.0,decay=0.0,batch_size=16,return_best_model=True,\
           pretrainingModif=True) 
    # A tester ! 
    
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP1',features='block5_pool',\
           constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
           transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
           regulOnNewLayer='l2',optimizer='SGD',opt_option=[0.1,0.01],\
           epochs=20,SGDmomentum=0.9,decay=1e-4,batch_size=16,return_best_model=True) 
    # & 15.7 & 15.3 & 69.2 & 49.4 & 19.6 & 33.6 & 18.2 & 43.1 & 26.7 & 44.0 & 33.5 \\ 
    
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='block5_pool',\
           constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
           transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
           regulOnNewLayer='l2',optimizer='SGD',opt_option=[0.1,0.01],\
           epochs=20,SGDmomentum=0.9,decay=1e-4,batch_size=16,return_best_model=True) 
    # ResNet50 GlobalAveragePooling2D ep :20 BFReLU & 17.8 & 13.3 & 62.6 & 41.0 & 13.7 & 32.0 & 16.8 & 29.3 & 13.6 & 32.6 & 27.3 \\ 
    
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='block5_pool',\
           constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
           transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
           regulOnNewLayer=None,optimizer='SGD',opt_option=[0.1,0.01],\
           epochs=20,SGDmomentum=0.9,decay=1e-4,batch_size=16,return_best_model=True,\
           pretrainingModif=True,verbose=True)  # Trainable params: 24,061,706 - Non-trainable params: 53,120
    # ResNet50 GlobalAveragePooling2D ep :20  
    #  & 16.9 & 13.2 & 64.9 & 34.1 & 14.5 & 33.2 & 17.7 & 30.7 & 16.7 & 48.8 & 29.1 \\
        
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='block5_pool',\
           constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
           transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
           regulOnNewLayer=None,optimizer='SGD',opt_option=[0.1,0.01],\
           epochs=20,SGDmomentum=0.9,decay=1e-4,batch_size=16,return_best_model=True,\
           pretrainingModif=106,verbose=True)  # A tester : à comparer a au dessus 
    # ResNet50 GlobalAveragePooling2D ep :20  
    #& 18.7 & 13.1 & 60.6 & 42.4 & 19.7 & 28.8 & 19.0 & 41.8 & 26.6 & 48.7 & 31.9 \\ 
    
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP2',features='block5_pool',\
       constrNet='ResNet50',kind_method='FT',gridSearch=False,ReDo=True,\
       transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
       regulOnNewLayer=None,optimizer='SGD',opt_option=[0.1,0.01],\
       epochs=20,SGDmomentum=0.9,decay=1e-4,batch_size=16,NoValidationSetUsed=True)
    #  & 12.2 & 11.0 & 67.5 & 34.0 & 15.7 & 29.5 & 20.2 & 31.8 & 23.9 & 23.6 & 26.9 \\ 
    
def testVGGShuffle():
    target_dataset = 'Paintings'
    ReDo = False
    epochs = 5
#    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
#               constrNet='VGG',kind_method='FT',gridSearch=True,ReDo=ReDo,\
#               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
#               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
#               epochs=epochs,nesterov=True,SGDmomentum=0.99,decay=0.0005)
#    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
#               constrNet='VGGBaseNormCoherentAdaIn',kind_method='FT',gridSearch=True,ReDo=ReDo,\
#               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
#               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
#               epochs=epochs,nesterov=True,SGDmomentum=0.99,decay=0.0005)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGFRN',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.99,decay=0.0005,getBeforeReLU=True)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGAdaIn',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.9,decay=0.0005)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGAdaIn',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.9,decay=0.0005)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGsuffleInStats',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,kind_of_shuffling='roll',\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.9,decay=0.0005)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGsuffleInStats',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,kind_of_shuffling='shuffle',\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.9,decay=0.0005)
    learn_and_eval(target_dataset,source_dataset='ImageNet',final_clf='MLP3',features='block5_pool',\
               constrNet='VGGAdaDBN',kind_method='FT',gridSearch=True,ReDo=ReDo,\
               transformOnFinalLayer='GlobalAveragePooling2D',cropCenter=True,kind_of_shuffling='shuffle',\
               dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[10**(-2)],\
               epochs=epochs,nesterov=True,SGDmomentum=0.9,decay=0.0005)

def testROWD_CUMUL():
    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
                    kind_method='TL',ReDo=False,gridSearch=False,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',\
                    useFloat32=True,computeGlobalVariance=True)
    # & 54.1 & 22.7 & 82.3 & 58.4 & 29.9 & 51.1 & 26.0 & 51.9 & 44.3 & 76.2 & 49.7 \\
    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
                    kind_method='TL',ReDo=False,gridSearch=True,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',\
                    useFloat32=True,computeGlobalVariance=True)
    #& 62.0 & 40.4 & 89.5 & 69.8 & 44.7 & 66.1 & 41.4 & 68.8 & 58.8 & 81.3 & 62.3 \\
    # Contre 72.2 pour LinearSVC sur les features directement...
        
def testROWD_CUMUL_FT_freezingLayers():
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,gridSearch=False,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',\
                    useFloat32=True,computeGlobalVariance=True,opt_option=[0.1,0.01],pretrainingModif=66,optimizer='SGD')

    
def test_avec_normalisation_ROWD_CUMUL():
#    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
#                    kind_method='TL',ReDo=True,
#                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
#                    style_layers=[],verbose=True,features='activation_48',useFloat32=True,
#                    normalisation=True,gridSearch=False)
    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
                    kind_method='TL',ReDo=False,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=['bn_conv1'],verbose=True,features='activation_48',useFloat32=True,
                    normalisation=True,gridSearch=False,computeGlobalVariance=True)
    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
                    kind_method='TL',ReDo=False,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',useFloat32=True,
                    normalisation=True,gridSearch=False,computeGlobalVariance=True)
    
def testROWD_CUMUL_and_BRNF_FineTuning():
    ### Non teste encore, non fonctionnel
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                    kind_method='FT',ReDo=True,
#                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
#                    style_layers=['bn_conv1'],verbose=True,features='activation_48',
#                    dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[0.1,10**(-2)],
#                    epochs=20,nesterov=True,SGDmomentum=0.99,return_best_model=True,batch_size=16)
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=True,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[0.1,10**(-2)],
                    epochs=20,nesterov=True,SGDmomentum=0.99,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True)
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                    kind_method='FT',ReDo=True,
#                    constrNet='ResNet50_BNRF',transformOnFinalLayer='GlobalAveragePooling2D',
#                    style_layers=[],verbose=True,features='activation_48',
#                    dropout=0.2,regulOnNewLayer='l2',optimizer='SGD',opt_option=[0.1,10**(-2)],
#                    epochs=20,nesterov=True,SGDmomentum=0.99,return_best_model=True,batch_size=16,
#                    batch_size_RF=16,epochs_RF=20,momentum=0.9)
#    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
#                    kind_method='TL',ReDo=False,
#                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
#                    style_layers=['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],\
#                    verbose=True,features='activation_48',useFloat32=True)
#    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
#                    kind_method='TL',ReDo=False,
#                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
#                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48,useFloat32=True')


def comparaison_ResNet_baseline_ResNetROWD_as_Init():
    
    ReDo = False
    
    ## Premier schema de fine tuning
    # La baseline TL
    # Trainable params: 527,114
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='TL',ReDo=ReDo,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=True,gridSearch=False)     
    # & 64.7 & 38.4 & 90.5 & 70.5 & 56.5 & 66.3 & 50.3 & 76.0 & 61.9 & 80.6 & 65.6 \\ 
    # & 57.1 & 38.3 & 89.7 & 69.0 & 52.2 & 62.1 & 50.4 & 74.9 & 60.7 & 77.5 & 63.2 \\ 
    # La baseline FT all freeze   
    # Trainable params: 527,114
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=False)
    # & 41.5 & 20.9 & 84.3 & 55.0 & 29.1 & 52.2 & 34.5 & 69.6 & 48.0 & 68.7 & 50.4 
    #  & 43.7 & 26.7 & 85.5 & 59.6 & 44.0 & 58.5 & 31.5 & 67.4 & 46.8 & 55.5 & 51.9 \\
    # La baseline FT all freeze 0 layers : test           
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=0)   
    #  & 29.2 & 23.5 & 85.9 & 56.6 & 42.2 & 62.9 & 37.3 & 70.2 & 39.5 & 61.9 & 50.9          
    # La baseline FT all fine-tune
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=True)            
    #& 15.9 & 15.4 & 64.0 & 48.2 & 17.1 & 34.1 & 20.6 & 35.1 & 23.8 & 40.3 & 31.4 \\ 
    # ResNet50_ROWD_CUMUL
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True)
    # & 62.5 & 42.1 & 92.4 & 73.2 & 59.3 & 69.3 & 51.2 & 76.9 & 67.2 & 85.7 & 68.0 \\
    # ResNet50_ROWD_CUMUL_AdaIn
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50_ROWD_CUMUL_AdaIn',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True)
    # & 44.7 & 38.6 & 88.7 & 71.0 & 45.3 & 65.0 & 44.9 & 71.6 & 54.1 & 80.6 & 60.5 \\ 
    # ResNet50_BNRF
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50_BNRF',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    batch_size_RF=16,epochs_RF=20,momentum=0.9)            
    # & 61.4 & 42.0 & 92.0 & 72.8 & 55.9 & 68.7 & 51.5 & 76.8 & 69.4 & 84.0 & 67.5 \\   
    # ResNet50_AdaIn
    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
                    kind_method='FT',ReDo=ReDo,
                    constrNet='ResNet50AdaIn',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    batch_size_RF=16,epochs_RF=20,momentum=0.9)            
    #  & 55.1 & 41.3 & 90.2 & 70.3 & 46.1 & 64.4 & 43.7 & 73.5 & 65.5 & 79.2 & 62.9 \\

#
#    # Deuxieme schema de fine tuning
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#            kind_method='FT',ReDo=False,
#            constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
#            style_layers=[],verbose=True,features='activation_48',
#            optimizer='SGD',opt_option=[0.1,10**(-2)],decay=10**(-4),SGDmomentum=0.9,
#            epochs=20,return_best_model=True,batch_size=16,
#            computeGlobalVariance=True,pretrainingModif=True) 
#    # & 13.6 & 13.2 & 49.5 & 45.0 & 19.1 & 34.1 & 16.2 & 39.6 & 23.0 & 49.1 & 30.2 \\ 
#    # Ne marche pas !!!
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#            kind_method='FT',ReDo=False,
#            constrNet='ResNet50AdaIn',transformOnFinalLayer='GlobalAveragePooling2D',
#            style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
#            optimizer='SGD',opt_option=[0.1,10**(-2)],decay=10**(-4),SGDmomentum=0.9,
#            epochs=20,return_best_model=True,batch_size=16,
#            computeGlobalVariance=False,pretrainingModif=True) 
#    #
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                kind_method='FT',ReDo=False,
#                constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
#                style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
#                optimizer='SGD',opt_option=[0.1,10**(-2)],decay=10**(-4),SGDmomentum=0.9,
#                epochs=20,return_best_model=True,batch_size=16,
#                computeGlobalVariance=True,pretrainingModif=True)  
    
def RASTAcomparaison_ResNet_baseline_ResNetROWD_as_Init():
    
    ## Premier schema de fine tuning
    # La baseline TL
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='TL',ReDo=False,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=True)     
    # & 64.7 & 38.4 & 90.5 & 70.5 & 56.5 & 66.3 & 50.3 & 76.0 & 61.9 & 80.6 & 65.6 \\ 
    # La baseline FT      
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,
                    constrNet='ResNet50',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=[],verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True,pretrainingModif=True)            
    #& 15.9 & 15.4 & 64.0 & 48.2 & 17.1 & 34.1 & 20.6 & 35.1 & 23.8 & 40.3 & 31.4 \\ 
    # ResNet50_ROWD_CUMUL
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,
                    constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True)
    # & 62.5 & 42.1 & 92.4 & 73.2 & 59.3 & 69.3 & 51.2 & 76.9 & 67.2 & 85.7 & 68.0 \\
    # ResNet50_ROWD_CUMUL_AdaIn
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,
                    constrNet='ResNet50_ROWD_CUMUL_AdaIn',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    computeGlobalVariance=True)
    # & 44.7 & 38.6 & 88.7 & 71.0 & 45.3 & 65.0 & 44.9 & 71.6 & 54.1 & 80.6 & 60.5 \\ 
    # ResNet50_BNRF
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,
                    constrNet='ResNet50_BNRF',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    batch_size_RF=16,epochs_RF=20,momentum=0.9)            
    # & 61.4 & 42.0 & 92.0 & 72.8 & 55.9 & 68.7 & 51.5 & 76.8 & 69.4 & 84.0 & 67.5 \\   
    # ResNet50_AdaIn
    learn_and_eval(target_dataset='RASTA',final_clf='MLP2',\
                    kind_method='FT',ReDo=False,
                    constrNet='ResNet50AdaIn',transformOnFinalLayer='GlobalAveragePooling2D',
                    style_layers=getBNlayersResNet50(),verbose=True,features='activation_48',
                    optimizer='SGD',opt_option=[10**(-2)],
                    epochs=20,return_best_model=True,batch_size=16,
                    batch_size_RF=16,epochs_RF=20,momentum=0.9)            
    # ?
 

       
# TODO :
# Train the layer i and use it as initialization for training layer i+1 
# Test RASTA
        
### What we could add to improve the model performance : 
# change the learning rate
# data augmentation
# dropout
# use of L1 and L2 regularization (also known as "weight decay")
                  
if __name__ == '__main__': 
    # Ce que l'on 
    #RunAllEvaluation()
    ### TODO !!!!! Need to add a unbalanced way to deal with the dataset
    #PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'Paintings',scenario=0,onlyPlot=True)
    #PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=0,onlyPlot=True)

#    PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'Paintings',scenario=4)
#    PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=4)
#    PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'Paintings',scenario=5)
#    PlotSomePerformanceVGG(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=5)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'Paintings',scenario=4)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=4)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'Paintings',scenario=5)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=5)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'Paintings',scenario=3)
#    PlotSomePerformanceResNet(metricploted='mAP',target_dataset = 'IconArt_v1',scenario=3)
#    PlotSomePerformanceVGG()
#    RunUnfreezeLayerPerformanceVGG()
#    RunEval_MLP_onConvBlock()
    
#    learn_and_eval(target_dataset='Paintings',constrNet='VGG',kind_method='FT',weights=None,epochs=20,transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',kind_method='FT',epochs=20,transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',kind_method='FT',epochs=20,transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',kind_method='FT',epochs=20,transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',kind_method='FT',epochs=20,pretrainingModif=False,transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50',kind_method='FT',epochs=20,pretrainingModif=False,transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='ResNet50AdaIn',kind_method='FT',epochs=2,style_layers=['bn_conv1','bn2a_branch1','bn3a_branch1','bn4a_branch1','bn5a_branch1'],transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)
###    .
##                   epochs=20,transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True)
##    learn_and_eval(target_dataset='Paintings',constrNet='VGGAdaIn',kind_method='FT',\
#                   epochs=20,transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='VGGAdaIn',weights=None,\
#                   kind_method='FT',getBeforeReLU=True,epochs=20,\
#                   transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True,\
#                   style_layers= ['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
#                                  'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
#                                  'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
#                                  'block5_conv1','block5_conv2','block5_conv3','block5_conv4'])
#    learn_and_eval(target_dataset='Paintings',constrNet='VGGAdaIn',weights='imagenet',\
#                   kind_method='FT',getBeforeReLU=True,epochs=20,\
#                   transformOnFinalLayer='GlobalMaxPooling2D',forLatex=True,\
#                   style_layers= ['block1_conv1','block1_conv2','block2_conv1','block2_conv2',
#                                  'block3_conv1','block3_conv2','block3_conv3','block3_conv4',
#                                  'block4_conv1','block4_conv2','block4_conv3','block4_conv4', 
#                                  'block5_conv1','block5_conv2','block5_conv3','block5_conv4'])
#    learn_and_eval(target_dataset='Paintings',constrNet='VGGAdaIn',\
#                   kind_method='FT',getBeforeReLU=True,epochs=20,transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)
#    learn_and_eval(target_dataset='Paintings',constrNet='VGG',pretrainingModif=False,\
#                   kind_method='FT',epochs=20,transformOnFinalLayer='GlobalAveragePooling2D',forLatex=True)

## Pour tester le MLP1 sur IconArt v1
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='VGG',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='fc2')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='VGG',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='block5_pool')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='ResNet50',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='ResNet50',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='avg_pool')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='VGGAdaIn',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='fc2')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='VGGAdaIn',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='block5_pool')
#    learn_and_eval(target_dataset='IconArt_v1',constrNet='VGG',kind_method='FT',weights='imagenet',epochs=5,final_clf='MLP1',features='fc2',pretrainingModif=6)

## To test return_best_model in FT mode and FT mode
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                        kind_method='FT',epochs=3,ReDo=True,optimizer='adam',\
#                        opt_option=[0.01],features='block5_pool',\
#                        batch_size=32,constrNet='VGG',freezingType='FromTop',\
#                        pretrainingModif=6,plotConv=True,transformOnFinalLayer='GlobalAveragePooling2D',return_best_model=True)
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                        kind_method='TL',epochs=3,ReDo=True,optimizer='adam',\
#                        opt_option=[0.01],features='block5_pool',\
#                        batch_size=32,constrNet='VGG',plotConv=True,\
#                        transformOnFinalLayer='GlobalAveragePooling2D',return_best_model=True)

## Test BN Refinement of ResNet50
    # learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
    #                     kind_method='TL',
    #                     constrNet='ResNet50_BNRF',batch_size_RF=16,\
    #                     style_layers=[],verbose=True,epochs_RF=20,\
    #                     transformOnFinalLayer='GlobalMaxPooling2D',\
    #                     features='activation_48',cropCenter=True)
## Test MLP2 with gridsearch
#    learn_and_eval(target_dataset='Paintings',final_clf='MLP2',\
#                        kind_method='TL',
#                        constrNet='ResNet50',batch_size=16,\
#                        style_layers=[],verbose=True,epochs=20,\
#                        transformOnFinalLayer='GlobalAveragePooling2D',\
#                        features='activation_48',cropCenter=True,gridSearch=True)
#    Crowley_reproduction_results()
## Test BN Refinement Once on the Whole Dataset of ResNet50
#    learn_and_eval(target_dataset='Paintings',final_clf='LinearSVC',\
#                        kind_method='TL',ReDo=True,
#                        constrNet='ResNet50_ROWD_CUMUL',transformOnFinalLayer='GlobalAveragePooling2D',
#                        style_layers=['bn_conv1'],verbose=True,features='activation_48') # A finir
#    testROWD_CUMUL()
#    RunAllEvaluation_ForFeatureExtractionModel()
#   comparaison_ResNet_baseline_ResNetROWD_as_Init()
    #RunAllEvaluation_ForFeatureExtractionModel(printForTabularLatex=True)
    #RunAllEvaluation_ForFeatureExtractionModel()
    #RunAllEvaluation_FineTuningResNet()
    PlotSomePerformanceResNet_V2(metricploted='mAP',target_dataset = 'Paintings',
                              onlyPlot=False,cropCenter=True,BV=True)
    RunAllEvaluation_FineTuningResNet()
    RunAllEvaluation_FineTuningVGG()   
    