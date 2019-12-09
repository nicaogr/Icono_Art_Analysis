#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 14:19:01 2019

The goal of this script is to study the impact of the refinement of the batch 
normalisation on the features of the ResNet model

@author: gonthier
"""

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
    vgg_FRN
from StatsConstr_ClassifwithTL import learn_and_eval

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
    fit_generator_ForRefineParameters

from preprocess_crop import load_and_crop_img,load_and_crop_img_forImageGenerator

from functools import partial
from sklearn.metrics import average_precision_score,make_scorer
from sklearn.model_selection import GridSearchCV

from sklearn.feature_selection import mutual_info_classif

def compare_new_normStats_for_ResNet(target_dataset='Paintings'):
    """ The goal of this function is to compare the new normalisation statistics of BN
    computed in the case of the adaptation of them 
    We will compare BNRF, ROWD (mean of variance) and variance global in the case 
    of ResNet50 """
    
    matplotlib.use('Agg') # To avoid to have the figure that's pop up during execution
    
    nets = ['ResNet50','ResNet50_ROWD_CUMUL','ResNet50_ROWD_CUMUL','ResNet50_BNRF']
    style_layers = getBNlayersResNet50()
    features = 'activation_48'
    normalisation = False
    final_clf= 'LinearSVC' # Don t matter
    source_dataset=  'ImageNet'
    kind_method=  'TL'
    transformOnFinalLayer='GlobalAveragePooling2D'
    computeGlobalVariance_tab = [False,False,True,False]
    cropCenter = True
    # Load ResNet50 normalisation statistics
    
    list_bn_layers = getBNlayersResNet50()

    Model_dict = {}
    list_markers = ['o','s','X','*']
    alpha = 0.7
    
    for constrNet,computeGlobalVariance in zip(nets,computeGlobalVariance_tab):          
        output = learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                               constrNet,kind_method,style_layers=style_layers,
                               normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                               batch_size_RF=16,epochs_RF=20,momentum=0.9,ReDo=False,
                               returnStatistics=True,cropCenter=cropCenter,\
                               computeGlobalVariance=computeGlobalVariance)
        if 'ROWD' in constrNet:
            dict_stats_target,list_mean_and_std_target = output
        else:
            dict_stats_target,list_mean_and_std_target = extract_Norm_stats_of_ResNet(output,\
                                                    res_num_layers=50,model_type=constrNet)
        str_model = constrNet
        if computeGlobalVariance:
            str_model += 'GlobalVar' 
        Model_dict[str_model] = dict_stats_target
      
    print('Plotting the statistics')
    output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp','Covdata',\
                               target_dataset,'CompBNstats') 
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pltname = 'ResNet50_comparison_BN_statistics_ROWD_and_BNRF'
    if cropCenter:
        pltname += '_cropCenter'   
    pltname +='.pdf'
    pltname= os.path.join(output_path,pltname)
    pp = PdfPages(pltname)    
    
    distances_means = {}
    distances_stds = {}
    ratios_means = {}
    ratios_stds = {}

    for layer_name in list_bn_layers:
        distances_means[layer_name] = []
        distances_stds[layer_name] = []
        ratios_means[layer_name] = []
        ratios_stds[layer_name] = []
        
        fig, (ax1, ax2) = plt.subplots(2, 1)
        str_title = 'Normalisation statistics ' + layer_name
        fig.suptitle(str_title)
        i = 0
        for constrNet,computeGlobalVariance in zip(nets,computeGlobalVariance_tab):
            str_model = constrNet
            if computeGlobalVariance:
                str_model += 'GlobalVar' 
            str_model.replace('ResNet50_','')
            dict_stats_target = Model_dict[str_model]
            stats_target =  dict_stats_target[layer_name]
            means,stds = stats_target
            if constrNet=='ResNet50':
                ref_means = means
                ref_stds = stds
            else:
                diff_means = np.abs(ref_means-means)
                diff_stds = np.abs(ref_stds-stds)
                ratio_means = np.abs(means/ref_means)
                ratio_stds = np.abs(stds/ref_stds)
                distances_means[layer_name] += [diff_means]
                distances_stds[layer_name] += [diff_stds]
                ratios_means[layer_name] += [ratio_means]
                ratios_stds[layer_name] += [ratio_stds]
            x = np.arange(0,len(means))
            ax1.scatter(x, means,label=str_model,marker=list_markers[i],alpha=alpha)
            ax1.set_title('Normalisation Means')
            ax1.set_xlabel('Channel')
            ax1.set_ylabel('Mean')
            ax1.tick_params(axis='both', which='major', labelsize=3)
            ax1.tick_params(axis='both', which='minor', labelsize=3)
            ax1.legend(loc='best', prop={'size': 4})
            ax2.scatter(x, stds,label=str_model,marker=list_markers[i],alpha=alpha)
            ax2.set_title('Normalisation STDs')
            ax2.set_xlabel('Channel')
            ax2.set_ylabel('Std')
            ax2.tick_params(axis='both', which='major', labelsize=3)
            ax2.tick_params(axis='both', which='minor', labelsize=3)
            ax2.legend(loc='best', prop={'size': 4})
            i+=1
 
        #plt.show()
        plt.savefig(pp, format='pdf')
        plt.close()
     
    # Plot the boxplot of the distance between normalisation statistics
    fig = plt.figure()
    ax = plt.axes()
    set_xticks= []
    c = ['C1','C2','C3']
    c = ['orange','green','red']
    for i,layer_name in enumerate(list_bn_layers):     
        positions = [i*3,i*3+1,i*3+2]
        set_xticks += [i*3+1]
        bp = plt.boxplot(np.log(distances_means[layer_name]).tolist(), positions = positions, 
                         widths = 0.6,notch=True, patch_artist=True)
        for patch, color in zip(bp['boxes'], c):
            patch.set_facecolor(color)
    ax.set_xticklabels(list_bn_layers)
    ax.set_xticks(set_xticks)
    plt.setp( ax.xaxis.get_majorticklabels(), rotation='vertical')
    hO, = plt.plot([1,1],'C1-')
    hG, = plt.plot([1,1],'C2-')
    hR, = plt.plot([1,1],'C3-')
    plt.title('Log Abs distance between means of refined and orignal.', fontsize=10)
    plt.legend((hO, hG,hR),('ROWD','ROWD_global', 'BNRF'))
    hO.set_visible(False)
    hG.set_visible(False)
    hR.set_visible(False)
    plt.savefig(pp, format='pdf')
    plt.close()
    
    fig = plt.figure()
    ax = plt.axes()
    set_xticks= []
    
    for i,layer_name in enumerate(list_bn_layers):     
        positions = [i*3,i*3+1,i*3+2]
        set_xticks += [i*3+1]
        bp = plt.boxplot(np.log(distances_stds[layer_name]).tolist(), positions = positions, 
                         widths = 0.6,notch=True, patch_artist=True)
        for patch, color in zip(bp['boxes'], c):
            patch.set_facecolor(color) 
    ax.set_xticklabels(list_bn_layers)
    ax.set_xticks(set_xticks)
    plt.setp( ax.xaxis.get_majorticklabels(), rotation='vertical')
    hO, = plt.plot([1,1],'C1-')
    hG, = plt.plot([1,1],'C2-')
    hR, = plt.plot([1,1],'C3-')
    plt.title('Log Abs distance between  stds of refined and orignal.', fontsize=10)
    plt.legend((hO, hG,hR),('ROWD','ROWD_global', 'BNRF'))
    hO.set_visible(False)
    hG.set_visible(False)
    hR.set_visible(False)
    plt.savefig(pp, format='pdf')
    plt.close()
    
    # Plot the boxplot of the ratio between normalisation statistics
    fig = plt.figure()
    ax = plt.axes()
    set_xticks= []
    c = ['C1','C2','C3']
    c = ['orange','green','red']
    for i,layer_name in enumerate(list_bn_layers):     
        positions = [i*3,i*3+1,i*3+2]
        set_xticks += [i*3+1]
        bp = plt.boxplot(np.log(1.+np.array(ratios_means[layer_name])).tolist(), positions = positions, 
                         widths = 0.6,notch=True, patch_artist=True)
        for patch, color in zip(bp['boxes'], c):
            patch.set_facecolor(color)
    ax.set_xticklabels(list_bn_layers)
    ax.set_xticks(set_xticks)
    plt.setp( ax.xaxis.get_majorticklabels(), rotation='vertical')
    hO, = plt.plot([1,1],'C1-')
    hG, = plt.plot([1,1],'C2-')
    hR, = plt.plot([1,1],'C3-')
    plt.title('Log 1+ Ratio between means of refined and orignal.', fontsize=10)
    plt.legend((hO, hG,hR),('ROWD','ROWD_global', 'BNRF'))
    hO.set_visible(False)
    hG.set_visible(False)
    hR.set_visible(False)
    plt.savefig(pp, format='pdf')
    plt.close()
    
    fig = plt.figure()
    ax = plt.axes()
    set_xticks= []
    
    for i,layer_name in enumerate(list_bn_layers):     
        positions = [i*3,i*3+1,i*3+2]
        set_xticks += [i*3+1]
        bp = plt.boxplot(np.log(1.+np.array(ratios_stds[layer_name])).tolist(), positions = positions, 
                         widths = 0.6,notch=True, patch_artist=True)
        for patch, color in zip(bp['boxes'], c):
            patch.set_facecolor(color) 
    ax.set_xticklabels(list_bn_layers)
    ax.set_xticks(set_xticks)
    plt.setp( ax.xaxis.get_majorticklabels(), rotation='vertical')
    hO, = plt.plot([1,1],'C1-')
    hG, = plt.plot([1,1],'C2-')
    hR, = plt.plot([1,1],'C3-')
    plt.title('Log 1+ ratio between stds of Refined model and original', fontsize=10)
    plt.legend((hO, hG,hR),('ROWD','ROWD_global', 'BNRF'))
    hO.set_visible(False)
    hG.set_visible(False)
    hR.set_visible(False)
    plt.savefig(pp, format='pdf')
    plt.close()
   
    pp.close()
    plt.clf()
    
    
def compute_MutualInfo(target_dataset='Paintings'):
    """ The goal of this function is to compute the entropy and the mutual information 
    of the features in the ResNet model and the refined versions 
    We will compare BNRF, ROWD (mean of variance) and variance global in the case 
    of ResNet50 """
    
    matplotlib.use('Agg') # To avoid to have the figure that's pop up during execution
    
    nets = ['ResNet50','ResNet50_ROWD_CUMUL','ResNet50_ROWD_CUMUL','ResNet50_BNRF']
    style_layers = getBNlayersResNet50()
    features = 'activation_48'
    normalisation = False
    final_clf= 'LinearSVC' # Don t matter
    source_dataset=  'ImageNet'
    kind_method=  'TL'
    transformOnFinalLayer='GlobalAveragePooling2D'
    computeGlobalVariance_tab = [False,False,True,False]
    cropCenter = True
    # Load ResNet50 normalisation statistics
    Model_dict = {}
    
    for constrNet,computeGlobalVariance in zip(nets,computeGlobalVariance_tab):    
        str_model = constrNet
        if computeGlobalVariance:
            str_model += 'GlobalVar'
        print(str_model)
        Model_dict[str_model] = {}
        
        output = learn_and_eval(target_dataset,source_dataset,final_clf,features,\
                               constrNet,kind_method,style_layers=style_layers,
                               normalisation=normalisation,transformOnFinalLayer=transformOnFinalLayer,
                               batch_size_RF=16,epochs_RF=20,momentum=0.9,ReDo=False,
                               returnFeatures=True,cropCenter=cropCenter,\
                               computeGlobalVariance=computeGlobalVariance)
        Xtrainval,ytrainval,X_test,y_test =  output
        _,num_classes = ytrainval.shape
        
        # Mutual Information
        for c in range(num_classes):
            print('For class',c)
            MI_trainval_c = mutual_info_classif(Xtrainval, ytrainval[:,c], discrete_features=False, n_neighbors=3, \
                                              copy=True, random_state=0)
            sum_MI_trainval_c = np.sum(MI_trainval_c)
            MI_test_c = mutual_info_classif(X_test, y_test[:,c], discrete_features=False, n_neighbors=3, \
                                              copy=True, random_state=0)
            sum_MI_test_c = np.sum(MI_test_c)
            Model_dict[str_model][c] = {}
            Model_dict[str_model][c]['trainval'] =  sum_MI_trainval_c
            Model_dict[str_model][c]['test'] =  sum_MI_test_c
     
    output_path = os.path.join(os.sep,'media','gonthier','HDD2','output_exp')
    
    if os.path.isdir(output_path):
        output_path_full = os.path.join(output_path,'Covdata')
    else:
        output_path_full = os.path.join('data','Covdata')
    filename_path = os.path.join(output_path_full,'MutualInfo_'+target_dataset+'.pkl')
    # Warning ici tu ecrases le meme fichier
    with open(filename_path, 'wb') as handle:
        pickle.dump(Model_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
            
    for c in range(num_classes):
        string = 'Classs '+str(c) 
        for set_ in ['trainval','test']:
            strings = string + ' '+set_
            for constrNet,computeGlobalVariance in zip(nets,computeGlobalVariance_tab):
                   str_model = constrNet
                   if computeGlobalVariance:
                       str_model += 'GlobalVar' 
                   strings += ' '+str_model + ' : '
                   sum_MI =  Model_dict[str_model][c][set_] 
                   strings += "{:.2E}".format(sum_MI) 
            strings += '\n'
            print(strings)
#            
#Classs 0 trainval ResNet50 : 4.39E+00 ResNet50_ROWD_CUMUL : 1.01E+01 ResNet50_ROWD_CUMULGlobalVar : 8.75E+00 ResNet50_BNRF : 4.98E+00
#
#Classs 0 test ResNet50 : 4.94E+00 ResNet50_ROWD_CUMUL : 7.03E+00 ResNet50_ROWD_CUMULGlobalVar : 5.85E+00 ResNet50_BNRF : 5.23E+00
#
#Classs 1 trainval ResNet50 : 5.42E+00 ResNet50_ROWD_CUMUL : 5.58E+00 ResNet50_ROWD_CUMULGlobalVar : 5.27E+00 ResNet50_BNRF : 4.77E+00
#
#Classs 1 test ResNet50 : 5.90E+00 ResNet50_ROWD_CUMUL : 9.65E+00 ResNet50_ROWD_CUMULGlobalVar : 6.51E+00 ResNet50_BNRF : 4.52E+00
#
#Classs 2 trainval ResNet50 : 3.26E+01 ResNet50_ROWD_CUMUL : 5.26E+01 ResNet50_ROWD_CUMULGlobalVar : 6.13E+01 ResNet50_BNRF : 7.90E+01
#
#Classs 2 test ResNet50 : 3.19E+01 ResNet50_ROWD_CUMUL : 6.09E+01 ResNet50_ROWD_CUMULGlobalVar : 6.84E+01 ResNet50_BNRF : 7.83E+01
#
#Classs 3 trainval ResNet50 : 2.57E+01 ResNet50_ROWD_CUMUL : 3.55E+01 ResNet50_ROWD_CUMULGlobalVar : 5.75E+01 ResNet50_BNRF : 4.64E+01
#
#Classs 3 test ResNet50 : 2.41E+01 ResNet50_ROWD_CUMUL : 3.11E+01 ResNet50_ROWD_CUMULGlobalVar : 5.17E+01 ResNet50_BNRF : 3.42E+01
#
#Classs 4 trainval ResNet50 : 1.01E+01 ResNet50_ROWD_CUMUL : 3.97E+00 ResNet50_ROWD_CUMULGlobalVar : 6.15E+00 ResNet50_BNRF : 9.46E+00
#
#Classs 4 test ResNet50 : 9.36E+00 ResNet50_ROWD_CUMUL : 4.71E+00 ResNet50_ROWD_CUMULGlobalVar : 6.26E+00 ResNet50_BNRF : 6.39E+00
#
#Classs 5 trainval ResNet50 : 1.83E+01 ResNet50_ROWD_CUMUL : 3.56E+01 ResNet50_ROWD_CUMULGlobalVar : 4.80E+01 ResNet50_BNRF : 3.88E+01
#
#Classs 5 test ResNet50 : 1.78E+01 ResNet50_ROWD_CUMUL : 3.28E+01 ResNet50_ROWD_CUMULGlobalVar : 4.24E+01 ResNet50_BNRF : 3.21E+01
#
#Classs 6 trainval ResNet50 : 9.25E+00 ResNet50_ROWD_CUMUL : 9.50E+00 ResNet50_ROWD_CUMULGlobalVar : 1.06E+01 ResNet50_BNRF : 1.03E+01
#
#Classs 6 test ResNet50 : 8.45E+00 ResNet50_ROWD_CUMUL : 8.69E+00 ResNet50_ROWD_CUMULGlobalVar : 1.04E+01 ResNet50_BNRF : 1.15E+01
#
#Classs 7 trainval ResNet50 : 1.48E+01 ResNet50_ROWD_CUMUL : 7.09E+00 ResNet50_ROWD_CUMULGlobalVar : 7.71E+00 ResNet50_BNRF : 9.26E+00
#
#Classs 7 test ResNet50 : 1.50E+01 ResNet50_ROWD_CUMUL : 6.25E+00 ResNet50_ROWD_CUMULGlobalVar : 7.49E+00 ResNet50_BNRF : 9.75E+00
#
#Classs 8 trainval ResNet50 : 1.18E+01 ResNet50_ROWD_CUMUL : 5.93E+00 ResNet50_ROWD_CUMULGlobalVar : 7.36E+00 ResNet50_BNRF : 1.37E+01
#
#Classs 8 test ResNet50 : 1.27E+01 ResNet50_ROWD_CUMUL : 4.99E+00 ResNet50_ROWD_CUMULGlobalVar : 6.32E+00 ResNet50_BNRF : 1.32E+01
#
#Classs 9 trainval ResNet50 : 1.01E+01 ResNet50_ROWD_CUMUL : 3.54E+00 ResNet50_ROWD_CUMULGlobalVar : 4.62E+00 ResNet50_BNRF : 1.45E+01
#
#Classs 9 test ResNet50 : 1.12E+01 ResNet50_ROWD_CUMUL : 6.62E+00 ResNet50_ROWD_CUMULGlobalVar : 8.64E+00 ResNet50_BNRF : 1.71E+01