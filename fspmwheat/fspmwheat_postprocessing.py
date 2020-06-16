# -*- coding: latin-1 -*-

import os
import pandas as pd
import numpy as np
import statsmodels.api as sm

from cnwheat import model as cnwheat_model


def leaf_traits(scenario_outputs_dirpath, scenario_postprocessing_dirpath):
    """
    Average RUE and photosynthetic yield for the whole cycle.

    :param str scenario_outputs_dirpath: the path to the CSV outputs file of the scenario
    :param str scenario_postprocessing_dirpath: the path to the CSV postprocessing file of the scenari
    """

    # --- Import simulations outputs/prostprocessings
    df_axe = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'axes_outputs.csv'))
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_hz = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'hiddenzones_outputs.csv'))

    # --- Extract key values per leaf
    res = df_hz.copy()
    res = res[(res['axis'] == 'MS') & (res['plant'] == 1) & ~np.isnan(res.leaf_Lmax)].copy()
    res_IN = res[~ np.isnan(res.internode_Lmax)]
    last_value_idx = res.groupby(['metamer'])['t'].transform(max) == res['t']
    res = res[last_value_idx].copy()
    res['lamina_Wmax'] = res.leaf_Wmax
    res['lamina_W_Lg'] = res.leaf_Wmax / res.lamina_Lmax
    last_value_idx = res_IN.groupby(['metamer'])['t'].transform(max) == res_IN['t']
    res_IN = res_IN[last_value_idx].copy()
    leaf_traits_df = res[['metamer', 'leaf_Lmax', 'leaf_Lmax_em', 'lamina_Lmax', 'sheath_Lmax', 'lamina_Wmax', 'lamina_W_Lg', 'SSLW', 'LSSW']].merge(res_IN[['metamer', 'internode_Lmax']],
                                                                                                                                                     left_on='metamer',
                                                                                                                                                     right_on='metamer',
                                                                                                                                                     how='outer').copy()
    # Lamina max width / max length at leaf emergence
    res_em = df_hz[(df_hz['axis'] == 'MS') & (df_hz['plant'] == 1) & ~np.isnan(df_hz.leaf_Wmax)].copy()
    em_idx = res_em.groupby(['metamer'])['t'].transform(min) == res_em['t']
    res_em = res_em[em_idx].copy()
    res_em['lamina_W_Lg_em'] = res_em.leaf_Wmax / res_em.lamina_Lmax
    leaf_traits_df = leaf_traits_df.merge(res_em[['metamer', 'lamina_W_Lg_em']], on='metamer', how='outer')

    # --- Simulated RER

    # import simulation outputs
    data_RER = df_hz.copy()
    data_RER = data_RER[(data_RER.axis == 'MS') & (data_RER.metamer >= 4)].copy()
    data_RER.sort_values(['t', 'metamer'], inplace=True)
    data_teq = df_axe.copy()
    data_teq = data_teq[data_teq.axis == 'MS'].copy()

    # Time previous leaf emergence
    tmp = data_RER[data_RER.leaf_is_emerged]
    leaf_em = tmp.groupby('metamer', as_index=False)['t'].min()
    leaf_em['t_em'] = leaf_em.t
    leaf_em = leaf_em.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    leaf_em['sumTT_em'] = leaf_em.sum_TT
    leaf_traits_df = leaf_traits_df.merge(leaf_em[['metamer', 't_em', 'sumTT_em']], on='metamer', how='outer')
    prev_leaf_em = leaf_em.copy()
    prev_leaf_em.metamer = leaf_em.metamer + 1
    prev_leaf_em['sumTT_em_prev'] = prev_leaf_em['sumTT_em']
    phyllo = leaf_em.merge(prev_leaf_em[['metamer', 'sumTT_em_prev']], on='metamer', how='outer')
    phyllo['phyllo_TT'] = phyllo.sumTT_em - phyllo.sumTT_em_prev
    leaf_traits_df = leaf_traits_df.merge(phyllo[['metamer', 'phyllo_TT', 'sumTT_em_prev']], on='metamer', how='outer')

    data_RER2 = pd.merge(data_RER, prev_leaf_em[['metamer', 't_em']], on='metamer')
    data_RER2 = data_RER2[data_RER2.t <= data_RER2.t_em]

    # SumTimeEq
    data_teq['SumTimeEq'] = np.cumsum(data_teq.delta_teq)
    data_RER3 = pd.merge(data_RER2, data_teq[['t', 'SumTimeEq']], on='t')

    # logL
    data_RER3['logL'] = np.log(data_RER3.leaf_L)

    # Estimate RER
    leaf_traits_df['RER'] = np.nan
    for leaf in data_RER3.metamer.drop_duplicates():
        Y = data_RER3.logL[data_RER3.metamer == leaf]
        X = data_RER3.SumTimeEq[data_RER3.metamer == leaf]
        X = sm.add_constant(X)
        mod = sm.OLS(Y, X)
        fit_RER = mod.fit()
        leaf_traits_df.loc[leaf_traits_df.metamer == leaf, 'RER'] = fit_RER.params['SumTimeEq']

    # --- Time of leaf initiation
    leaf_init = df_hz.groupby('metamer', as_index=False)['t'].min()
    leaf_init.loc[leaf_init.t == 0, 't'] = np.nan
    leaf_init['t_init'] = leaf_init.t
    leaf_init = leaf_init.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    leaf_init['sumTT_init'] = leaf_init.sum_TT
    leaf_traits_df = leaf_traits_df.merge(leaf_init[['metamer', 'sumTT_init']], on='metamer', how='outer')
    leaf_traits_df['ageTT_init_em_prev'] = leaf_traits_df.sumTT_em_prev - leaf_traits_df.sumTT_init

    # --- Time ligulation
    df_lam = df_elt[(df_elt.axis == 'MS') & (df_elt.element == 'LeafElement1')].copy()
    df_lam_green = df_lam[(~df_lam.is_growing) & (df_lam.senesced_mstruct == 0)]
    lamina_lig = df_lam_green.groupby('metamer', as_index=False)['t'].min()
    lamina_lig['t_lig'] = lamina_lig.t
    lamina_lig = lamina_lig.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    lamina_lig['sumTT_lig'] = lamina_lig.sum_TT
    leaf_traits_df = leaf_traits_df.merge(lamina_lig[['metamer', 't_lig', 'sumTT_lig']], on='metamer', how='outer')
    leaf_traits_df.loc[leaf_traits_df['metamer'] < 3, 't_lig'] = np.nan
    leaf_traits_df.loc[leaf_traits_df['metamer'] < 3, 'sumTT_lig'] = np.nan
    leaf_traits_df['ageTT_lig'] = leaf_traits_df.sumTT_lig - leaf_traits_df.sumTT_em

    # --- Time onset of senescence
    tmp = df_lam[df_lam.senesced_mstruct > 0]
    tmp2 = tmp.groupby('metamer', as_index=False)['t'].min()
    tmp2['t_senesc_onset'] = tmp2.t
    tmp2 = tmp2.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    tmp2['sumTT_senesc_onset'] = tmp2.sum_TT
    leaf_traits_df = leaf_traits_df.merge(tmp2[['metamer', 't_senesc_onset', 'sumTT_senesc_onset']], on='metamer', how='outer')
    leaf_traits_df['ageTT_senesc_onset'] = leaf_traits_df.sumTT_senesc_onset - leaf_traits_df.sumTT_em

    # --- Time end of senescence
    tmp = df_lam[df_lam.mstruct == 0]
    tmp2 = tmp.groupby('metamer', as_index=False)['t'].min()
    tmp2['t_senesc_end'] = tmp2.t
    tmp2 = tmp2.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    tmp2['sumTT_senesc_end'] = tmp2.sum_TT
    leaf_traits_df = leaf_traits_df.merge(tmp2[['metamer', 't_senesc_end', 'sumTT_senesc_end']], on='metamer', how='outer')
    leaf_traits_df['ageTT_senesc_end'] = leaf_traits_df.sumTT_senesc_end - leaf_traits_df.sumTT_em

    # --- Lifespan
    leaf_traits_df['lifespanTT_lig_green'] = leaf_traits_df.sumTT_senesc_onset - leaf_traits_df.sumTT_lig
    leaf_traits_df['lifespanTT_lig'] = leaf_traits_df.sumTT_senesc_end - leaf_traits_df.sumTT_lig

    # --- Mean SLA and SLN in between ligulation and onset of senescence
    leaf_traits_df = leaf_traits_df.merge(df_lam_green.groupby('metamer', as_index=False).aggregate({'SLN': 'mean', 'SLA': 'mean'}), on='metamer', how='outer')

    # --- Save results in postprocessing directory
    leaf_traits_df.sort_values('metamer', inplace=True)
    leaf_traits_df.to_csv(os.path.join(scenario_postprocessing_dirpath, 'leaf_traits.csv'), index=False, na_rep='NA')


def canopy_kinetics(scenario_outputs_dirpath, scenario_postprocessing_dirpath, meteo_dirpath, plant_density=250):
    """
    Kinetic of variables at canopy level

    :param str scenario_outputs_dirpath: the path to the output CSV files of the scenario
    :param str scenario_postprocessing_dirpath: the path to the postprocessing CSV files of the scenario
    :param str meteo_dirpath: the path to the CSV meteo file
    :param int plant_density: the plant density (plant m-2)
    """

    # --- Import simulations outputs/prostprocessings
    df_axe = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'axes_outputs.csv'))
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_hz = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'hiddenzones_outputs.csv'))

    # --- Import meteo file for incident PAR
    df_meteo = pd.read_csv(meteo_dirpath)
    df_meteo['day'] = df_meteo.t // 24 + 1

    # --- LAI
    df_LAI = df_elt[(df_elt.element == 'LeafElement1')].groupby(['t'], as_index=False).agg({'green_area': 'sum'})
    df_LAI['LAI'] = df_LAI.green_area * plant_density
    df_LAI['day'] = df_LAI.t // 24 + 1
    df_LAI_days = df_LAI.groupby('day', as_index=False).agg({'LAI': 'mean'})
    canopy_df = df_LAI_days[['day', 'LAI']]

    # ## ----------  GLN / GAI
    #
    # ## -- Senescing area
    # leaf_ligulation = df_elt[(df_elt.element == 'LeafElement1') & (df_elt.is_growing == 0)].groupby('metamer').agg({'t': 'min'})
    # leaf_ligulation = leaf_ligulation.t.to_dict()
    #
    # df_elt_max_ga = df_elt[(df_elt.element == 'LeafElement1')].groupby(['metamer']).agg({'green_area_rep': 'max', 'green_area': 'max'})
    # df_elt_max_ga['green_area_rep_max'] = df_elt_max_ga.green_area_rep
    # df_elt_max_ga['green_area_max'] = df_elt_max_ga.green_area
    # df_elt_max_ga['metamer'] = df_elt_max_ga.index
    #
    # df_senesc = df_elt[(df_elt.element == 'LeafElement1')].merge(df_elt_max_ga[['green_area_rep_max', 'green_area_max', 'metamer']], left_on='metamer', right_on='metamer').copy()
    # df_senesc['senesc_area_rep'] = 0.
    # df_senesc['senesc_area'] = 0.
    # for i in df_senesc.index:
    #     if df_senesc.at[i, 't'] > leaf_ligulation.get(df_senesc.at[i, 'metamer'], 5000):
    #         df_senesc.at[i, 'senesc_area_rep'] = df_senesc.at[i, 'green_area_rep_max'] - df_senesc.at[i, 'green_area_rep']
    #         df_senesc.at[i, 'senesc_area'] = df_senesc.at[i, 'green_area_max'] - df_senesc.at[i, 'green_area']
    #
    # tmp = expand_grid({'t': df_senesc.t.drop_duplicates(), 'metamer': df_senesc.metamer.drop_duplicates()})
    # tmp2 = tmp.merge(df_elt_max_ga[['metamer', 'green_area_rep_max', 'green_area_max']], left_on=['metamer'], right_on=['metamer'], how='left')
    # tmp2['fully_senesc_area_rep'] = tmp2.green_area_rep_max
    # tmp2['fully_senesc_area'] = tmp2.green_area_max
    #
    # tmp3 = tmp2[['t', 'metamer', 'fully_senesc_area', 'fully_senesc_area_rep']].merge(df_senesc, left_on=['t', 'metamer'], right_on=['t', 'metamer'], how='left')
    # tmp3['senesc_area_all'] = 0.
    # tmp3['senesc_area_all_rep'] = 0.
    # for i in tmp3.index:
    #     if tmp3.at[i, 't'] < leaf_emergence.get((1, tmp3.at[i, 'metamer']), 0):
    #         tmp3.at[i, 'senesc_area_all_rep'] = 0
    #         tmp3.at[i, 'senesc_area_all'] = 0
    #     else:
    #         if np.isnan(tmp3['senesc_area_rep'][i]):
    #             tmp3.at[i, 'senesc_area_all_rep'] = tmp3.at[i, 'fully_senesc_area_rep']
    #             tmp3.at[i, 'senesc_area_all'] = tmp3.at[i, 'fully_senesc_area']
    #         else:
    #             tmp3.at[i, 'senesc_area_all_rep'] = tmp3.at[i, 'senesc_area_rep']
    #             tmp3.at[i, 'senesc_area_all'] = tmp3.at[i, 'senesc_area']
    #
    # # Percentage of green area (only true for leaves that get ligulated during the simulation)
    # tmp3['Pge_green_MS'] = tmp3.green_area / tmp3.green_area_max
    # tmp3['Pge_green_rep'] = tmp3.green_area_rep / tmp3.green_area_rep_max
    #
    # df_senesc_tot = tmp3.groupby(['t']).agg({'senesc_area_all_rep': 'sum', 'Pge_green_MS': 'sum'})
    # df_senesc_tot['t'] = df_senesc_tot.index
    #
    # df_LAI = df_LAI.merge(df_senesc_tot, left_on='t', right_on='t').copy()
    # df_LAI['LAI_all'] = df_LAI.LAI + df_LAI.senesc_area_all_rep * PLANT_DENSITY[plant]
    #
    # df_LAI['day'] = df_LAI.t // 24 + 1
    # LAI = df_LAI.groupby(['day']).agg({'LAI': 'mean'})
    # LAI_all = df_LAI.groupby(['day']).agg({'LAI_all': 'mean'})
    #
    # LAI = LAI.merge(out_sam_days[['day', 'sum_TT', 'TT']], on='day').copy()
    # LAI_all = LAI_all.merge(out_sam_days[['day', 'sum_TT', 'TT']], on='day').copy()
    #
    # ## -- Green Area Index (GAI)
    #
    # tmp = df_elt[(df_elt.organ == 'sheath')].groupby(['t', 'metamer'], as_index=False).agg({'green_area_rep': 'sum'})
    # S_gaines = tmp.groupby(['t'], as_index=False).agg({'green_area_rep': 'sum'})
    # S_gaines['S_GAI'] = S_gaines.green_area_rep / 2
    # S_gaines['day'] = S_gaines.t // 24 + 1
    # S_gaines_days = S_gaines.groupby(['day'], as_index=False).agg({'S_GAI': 'mean'})
    # GAI = LAI.merge(S_gaines_days, on='day')
    # GAI['GAI'] = GAI.LAI + GAI.S_GAI
    #
    # TT_Abichou9 = [570.79, 593.26, 719.1, 768.54, 1006.74, 1020.22]
    # GAI_Abichou9 = [0.4127, 0.5137, 0.6687, 0.7377, 3.9999, 4.2039]
    #
    # TT_Abichou10 = [560.15, 587.45, 709.55, 763.86, 1024.72, 1024.82, 1025.18, 1297.87, 1302.11, 1306.58, 1640.39, 1649.14, 1649.73]
    # GAI_Abichou10 = [0.3575, 0.484, 0.6576, 0.7794, 3.9037, 3.9049, 4.3055, 5.9101, 5.9272, 5.6305, 5.3831, 5.3654, 5.3641]
    #
    # TT_Abichou8 = [265.72, 335.37, 387.63, 439.85, 518.14, 631.16, 835.52, 900.7, 1022.51, 1104.92, 1405]
    # GAI_Abichou8 = [0.1457, 0.2526, 0.3064, 0.4307, 0.6964, 1.1917, 1.9883, 2.3066, 2.6788, 3.3675, 4.4124]
    #
    # ## -- GLN
    # GLN_Abichou_TT = [246, 299, 357, 383, 456, 498, 559, 704, 792, 846, 903, 1010, 1083, 1186, 1290, 1378, 1469, 1565, 1672, 1806, 1947]
    # GLN_Abichou_GLN = [1.1, 1.7, 1.9, 2.8, 3.8, 4.3, 5, 3.8, 3.7, 3.8, 3.4, 3.8, 4.3, 4, 3.8, 3.3, 2.9, 2.8, 2.3, 1.7, 0.9]
    #
    # GLN_Abichou_TT2 = [238, 295, 341, 451, 485, 561, 705, 796, 834, 890, 1008, 1076, 1186, 1289, 1380, 1466, 1602, 1712, 1871, 1958]
    # GLN_Abichou_GLN2 = [1.1, 1.8, 2.6, 3.6, 4.4, 5, 4.7, 3.9, 3.7, 3.9, 3.8, 4.4, 5, 5, 4.8, 4.1, 3.6, 2.9, 2.4, 2.1]
    #
    # GLN_Abichou_TT3 = [154, 204, 250, 258, 292, 380, 411, 442, 488, 534, 576, 603, 667, 727, 810, 989, 1065, 1275, 1362, 1524, 1835]
    # GLN_Abichou_GLN3 = [0.3, 0.7, 1.2, 1.4, 1.7, 2.5, 2.7, 3.1, 3.5, 3.8, 4.3, 4.4, 4.3, 4.2, 3.5, 4, 4.5, 5.6, 5.3, 4.7, 2.5]
    #
    # GLN_Abichou_TT4 = [393, 488, 548, 598, 659, 700, 829, 898, 970, 1038, 1122, 1372, 1440, 1524, 1782, 1972, 2192]
    # GLN_Abichou_GLN4 = [2.8, 3.7, 4.3, 4.5, 5.4, 5, 3.6, 3.8, 4.5, 5.2, 5.4, 5.5, 5.6, 5.4, 4.5, 2.5, 0]
    #
    # df_senesc_tot = df_senesc_tot.merge(out_sam[['t', 'sum_TT']], left_on='t', right_on='t').copy()
    # tmp = df_senesc_tot[(df_senesc_tot.t < leaf_emergence[(1, 9)]) & (df_senesc_tot.Pge_green_MS != 0.)].copy()  # only valid before emergence of lamina 9 because we don't knpw its final length
    #
    # df_gln = tmp

    # --- Ratio of incident PAR that is absorbed by the plant
    df_elt['PARa_surface'] = df_elt.PARa * df_elt.green_area * plant_density
    df_elt['PARa_surface2'] = df_elt.PARa * df_elt.green_area
    tutu = df_elt.groupby(['t'], as_index=False).agg({'PARa_surface': 'sum',
                                                      'green_area': 'sum'})
    tutu = tutu.merge(df_meteo, on='t').copy()
    tutu['ratio_PARa_PARi'] = tutu.PARa_surface / tutu.PARi

    tutu_days = tutu.groupby(['day'], as_index=False).agg({'PARa_surface': 'sum',
                                                           'PARi': 'sum',
                                                           'green_area': 'mean',
                                                           'ratio_PARa_PARi': 'mean',
                                                           't': 'min'})
    canopy_df = canopy_df.merge(tutu_days[['day', 't', 'ratio_PARa_PARi']], on='day', how='outer')

    # --- Surfacic PAR absorbed per day
    tmp = df_elt[df_elt['element'].isin(['StemElement', 'LeafElement1'])]
    tutu2 = tmp.groupby(['t'], as_index=False).agg({'PARa_surface2': 'sum',
                                                    'green_area': 'sum'})
    tutu2 = tutu2.merge(df_meteo, on='t').copy()
    tutu2_days = tutu2.groupby(['day'], as_index=False).agg({'PARa_surface2': 'sum',
                                                             'PARi': 'sum',
                                                             'green_area': 'mean'})
    tutu2_days['PARa_surfacique'] = tutu2_days.PARa_surface2 / tutu2_days.green_area
    tutu2_days['PARa_mol_m2_d'] = tutu2_days['PARa_surfacique'] * 3600 * 10 ** -6

    canopy_df = canopy_df.merge(tutu2_days[['day', 'PARa_mol_m2_d']], on='day', how='outer')

    # --- Save canopy_df
    canopy_df.to_csv(os.path.join(scenario_postprocessing_dirpath, 'canopy_kinetics_daily.csv'), index=False)


def table_C_usages(scenario_postprocessing_dirpath):
    """ Calculate C usage from postprocessings and save it to a CSV file

    :param str scenario_postprocessing_dirpath: the path to the CSV file describing all scenarii

    """
    # --- Import simulations prostprocessings
    df_axe = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'axes_postprocessing.csv'))
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_org = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'organs_postprocessing.csv'))
    df_hz = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'hiddenzones_postprocessing.csv'))

    df_roots = df_org[df_org['organ'] == 'roots'].copy()
    df_phloem = df_org[df_org['organ'] == 'phloem'].copy()

    # --- C usages relatif to Net Photosynthesis
    AMINO_ACIDS_C_RATIO = cnwheat_model.EcophysiologicalConstants.AMINO_ACIDS_C_RATIO  #: Mean number of mol of C in 1 mol of the major amino acids of plants (Glu, Gln, Ser, Asp, Ala, Gly)
    AMINO_ACIDS_N_RATIO = cnwheat_model.EcophysiologicalConstants.AMINO_ACIDS_N_RATIO  #: Mean number of mol of N in 1 mol of the major amino acids of plants (Glu, Gln, Ser, Asp, Ala, Gly)

    # Photosynthesis
    df_elt['Photosynthesis_tillers'] = df_elt['Photosynthesis'].fillna(0) * df_elt['nb_replications'].fillna(1.)
    Tillers_Photosynthesis_Ag = df_elt.groupby(['t'], as_index=False).agg({'Photosynthesis_tillers': 'sum'})
    C_usages = pd.DataFrame({'t': Tillers_Photosynthesis_Ag['t']})
    C_usages['C_produced'] = np.cumsum(Tillers_Photosynthesis_Ag.Photosynthesis_tillers)

    # Respiration
    C_usages['Respi_roots'] = np.cumsum(df_axe.C_respired_roots)
    C_usages['Respi_shoot'] = np.cumsum(df_axe.C_respired_shoot)

    # Exudation
    C_usages['exudation'] = np.cumsum(df_axe.C_exudated.fillna(0))

    # Structural growth
    C_consumption_mstruct_roots = df_roots.sucrose_consumption_mstruct.fillna(0) + df_roots.AA_consumption_mstruct.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    C_usages['Structure_roots'] = np.cumsum(C_consumption_mstruct_roots.reset_index(drop=True))

    df_hz['C_consumption_mstruct'] = df_hz.sucrose_consumption_mstruct.fillna(0) + df_hz.AA_consumption_mstruct.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_hz['C_consumption_mstruct_tillers'] = df_hz['C_consumption_mstruct'] * df_hz['nb_replications']
    C_consumption_mstruct_shoot = df_hz.groupby(['t'])['C_consumption_mstruct_tillers'].sum()
    C_usages['Structure_shoot'] = np.cumsum(C_consumption_mstruct_shoot.reset_index(drop=True))

    # Non structural C
    df_phloem['C_NS'] = df_phloem.sucrose.fillna(0) + df_phloem.amino_acids.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    C_NS_phloem_init = df_phloem.C_NS - df_phloem.C_NS.reset_index(drop=True)[0]
    C_usages['NS_phloem'] = C_NS_phloem_init.reset_index(drop=True)

    df_elt['C_NS'] = df_elt.sucrose.fillna(0) + df_elt.fructan.fillna(0) + df_elt.starch.fillna(0) + (
            df_elt.amino_acids.fillna(0) + df_elt.proteins.fillna(0)) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_elt['C_NS_tillers'] = df_elt['C_NS'] * df_elt['nb_replications'].fillna(1.)
    C_elt = df_elt.groupby(['t']).agg({'C_NS_tillers': 'sum'})

    df_hz['C_NS'] = df_hz.sucrose.fillna(0) + df_hz.fructan.fillna(0) + (df_hz.amino_acids.fillna(0) + df_hz.proteins.fillna(0)) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_hz['C_NS_tillers'] = df_hz['C_NS'] * df_hz['nb_replications'].fillna(1.)
    C_hz = df_hz.groupby(['t']).agg({'C_NS_tillers': 'sum'})

    df_roots['C_NS'] = df_roots.sucrose.fillna(0) + df_roots.amino_acids.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO

    C_NS_autre = df_roots.C_NS.reset_index(drop=True) + C_elt.C_NS_tillers.reset_index(drop=True) + C_hz.C_NS_tillers.reset_index(drop=True)
    C_NS_autre_init = C_NS_autre - C_NS_autre.reset_index(drop=True)[0]
    C_usages['NS_other'] = C_NS_autre_init.reset_index(drop=True)

    # Total
    C_usages['C_budget'] = (C_usages.Respi_roots + C_usages.Respi_shoot + C_usages.exudation + C_usages.Structure_roots + C_usages.Structure_shoot + C_usages.NS_phloem + C_usages.NS_other) / \
                           C_usages.C_produced

    C_usages.to_csv(os.path.join(scenario_postprocessing_dirpath, 'C_usages.csv'), index=False)


def calculate_performance_indices(scenario_outputs_dirpath, scenario_postprocessing_dirpath, meteo_dirpath, plant_density):
    """
    Average RUE and photosynthetic yield for the whole cycle.

    :param str scenario_outputs_dirpath: the path to the output CSV files of the scenario
    :param str scenario_postprocessing_dirpath: the path to the postprocessing CSV files of the scenario
    :param str meteo_dirpath: the path to the CSV meteo file
    :param int plant_density: the plant density (plant m-2)
    """

    # --- Import simulations prostprocessings and outputs
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_axe = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'axes_postprocessing.csv'))
    df_axe_out = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'axes_outputs.csv'))

    # --- Import meteo file for incident PAR
    df_meteo = pd.read_csv(meteo_dirpath)

    # --- RUE (g DM. MJ-1 PARa)
    df_elt['PARa_MJ'] = df_elt['PARa'] * df_elt['green_area'] * df_elt['nb_replications'].fillna(
        1.) * 3600 / 4.6 * 10 ** -6  # Si tallage, il faut alors utiliser les calculcs green_area et PARa des talles.
    df_elt['RGa_MJ'] = df_elt['PARa'] * df_elt['green_area'] * df_elt['nb_replications'].fillna(
        1.) * 3600 / 2.02 * 10 ** -6  # Si tallage, il faut alors utiliser les calculcs green_area et PARa des talles.
    PARa = df_elt.groupby(['t'])['PARa_MJ'].agg('sum')
    PARa_cum = np.cumsum(PARa)

    RUE_shoot = np.polyfit(PARa_cum, df_axe.sum_dry_mass_shoot, 1)[0]
    RUE_plant = np.polyfit(PARa_cum, df_axe.sum_dry_mass, 1)[0]

    # --- RUE (g DM. MJ-1 RGint estimated from LAI using Beer-Lambert's law with extinction coefficient of 0.4)

    # Beer-Lambert
    df_LAI = df_elt[(df_elt.element == 'LeafElement1')].groupby(['t']).agg({'green_area': 'sum'})
    df_LAI['LAI'] = df_LAI.green_area * plant_density
    df_LAI['t'] = df_LAI.index

    toto = df_meteo[['t', 'PARi']].merge(df_LAI[['t', 'LAI']], on='t', how='inner')
    toto['PARint_BL'] = toto.PARi * (1 - np.exp(-0.4 * toto.LAI))
    toto['RGint_BL_MJ'] = toto['PARint_BL'] * 3600 / 2.02 * 10 ** -6
    RGint_BL_cum = np.cumsum(toto.RGint_BL_MJ)

    df_axe['sum_dry_mass_shoot_couvert'] = df_axe.sum_dry_mass_shoot * plant_density
    df_axe['sum_dry_mass_couvert'] = df_axe.sum_dry_mass * plant_density

    RUE_shoot_couvert = np.polyfit(RGint_BL_cum, df_axe.sum_dry_mass_shoot_couvert, 1)[0]
    RUE_plant_couvert = np.polyfit(RGint_BL_cum, df_axe.sum_dry_mass_couvert, 1)[0]

    # ---  Photosynthetic efficiency of the plant
    df_elt['Photosynthesis_tillers'] = df_elt.Ag * df_elt.green_area * df_elt.nb_replications.fillna(1.)
    df_elt['PARa_tot_tillers'] = df_elt.PARa * df_elt.green_area * df_elt.nb_replications.fillna(1.)
    # df_elt['green_area_tillers'] = df_elt.green_area * df_elt.nb_replications.fillna(1.)
    # photo_y = df_elt.groupby(['t'],as_index=False).agg({'Photosynthesis_tillers':'sum', 'PARa_tot_tillers':'sum', 'green_area_tillers':'sum'})
    # photo_y['Photosynthetic_yield_plante'] = photo_y.Photosynthesis_tillers / photo_y.PARa_tot_tillers

    PARa2 = df_elt.groupby(['t'])['PARa_tot_tillers'].agg('sum')
    PARa2_cum = np.cumsum(PARa2)
    Photosynthesis = df_elt.groupby(['t'])['Photosynthesis_tillers'].agg('sum')
    Photosynthesis_cum = np.cumsum(Photosynthesis)

    avg_photo_y = np.polyfit(PARa2_cum, Photosynthesis_cum, 1)[0]

    # --- Photosynthetic C allocated to Respiration and to Exudation
    C_usages_path = os.path.join(scenario_postprocessing_dirpath, 'C_usages.csv')
    C_usages = pd.read_csv(C_usages_path)
    C_usages_div = C_usages.div(C_usages.C_produced, axis=0)

    # --- Final canopy traits
    t_end = max(df_elt.t)
    df_lamina = df_elt[df_elt.element == 'LeafElement1'].copy()
    df_lamina_end = df_lamina[(df_lamina.t == t_end)]
    nb_final_em_leaves = max(df_lamina_end.metamer)
    nb_final_lig_leaves = max(df_lamina_end[~df_lamina_end.is_growing].metamer)

    # final average SLA
    df_lamina_end_green = df_lamina_end[(df_lamina_end.green_area > 0) & (df_lamina_end.mstruct > 0)]
    if df_lamina_end_green.shape[0] > 1:
        final_avg_SLA = sum(df_lamina_end_green.green_area) / (sum(df_lamina_end_green.sum_dry_mass) * 10 ** -3)
    else:
        final_avg_SLA = np.nan

    # --- Mean canopy traits

    # average phyllochron
    avg_phyllo_df = df_lamina.groupby('metamer', as_index=False).agg({'t': 'min'})
    avg_phyllo_df = avg_phyllo_df.merge(df_axe_out[['t', 'sum_TT']], on='t')
    avg_phyllo_df = avg_phyllo_df[avg_phyllo_df.t > 0]
    Y = avg_phyllo_df['metamer']
    X = avg_phyllo_df['sum_TT']
    X = sm.add_constant(X)
    mod = sm.OLS(Y, X)
    fit_phyllo = mod.fit()

    # --- mean RGR
    df_axe['day'] = df_axe.t // 24 + 1
    df_axe = df_axe.merge(df_axe_out[['t', 'sum_TT']], on='t')
    df_RGR = df_axe.groupby('day', as_index=False).agg({'sum_dry_mass': 'max',
                                                        'sum_dry_mass_shoot': 'max',
                                                        'sum_dry_mass_roots': 'max',
                                                        'sum_TT': 'max'})
    df_RGR_prev = df_RGR.copy()
    df_RGR_prev.day = df_RGR_prev.day + 1
    df_RGR_prev['sum_dry_mass_prev'] = df_RGR_prev.sum_dry_mass
    df_RGR_prev['sum_dry_mass_shoot_prev'] = df_RGR_prev.sum_dry_mass_shoot
    df_RGR_prev['sum_dry_mass_roots_prev'] = df_RGR_prev.sum_dry_mass_roots
    df_RGR_prev['sum_TT_prev'] = df_RGR_prev.sum_TT
    df_RGR = df_RGR.merge(df_RGR_prev[['day', 'sum_TT_prev', 'sum_dry_mass_prev', 'sum_dry_mass_shoot_prev', 'sum_dry_mass_roots_prev']], on='day')
    df_RGR['delta_sum_TT'] = df_RGR.sum_TT - df_RGR.sum_TT_prev
    df_RGR['delta_sum_dry_mass'] = df_RGR.sum_dry_mass - df_RGR.sum_dry_mass_prev
    df_RGR['delta_sum_dry_mass_shoot'] = df_RGR.sum_dry_mass_shoot - df_RGR.sum_dry_mass_shoot_prev
    df_RGR['delta_sum_dry_mass_roots'] = df_RGR.sum_dry_mass_roots - df_RGR.sum_dry_mass_roots_prev
    df_RGR['RGR'] = df_RGR.delta_sum_dry_mass / df_RGR.sum_dry_mass
    df_RGR['RGR_shoot'] = df_RGR.delta_sum_dry_mass_shoot / df_RGR.sum_dry_mass_shoot
    df_RGR['RGR_roots'] = df_RGR.delta_sum_dry_mass_roots / df_RGR.sum_dry_mass_roots
    df_RGR['RGR_TT'] = df_RGR.RGR / df_RGR.delta_sum_TT
    df_RGR['RGR_shoot_TT'] = df_RGR.RGR_shoot / df_RGR.delta_sum_TT
    df_RGR['RGR_roots_TT'] = df_RGR.RGR_roots / df_RGR.delta_sum_TT

    # --- mean NAR: Net Assimilation Rate : delta g DM m-2 �Cd-1
    df_lamina_tot = df_lamina.groupby(['t'], as_index=False).agg({'green_area': 'sum',
                                                                  'sum_dry_mass': 'sum'})
    df_lamina_tot['day'] = df_lamina_tot.t // 24 + 1
    df_lamina_day_tot = df_lamina_tot.groupby(['day'], as_index=False).agg({'green_area': 'max',
                                                                            'sum_dry_mass': 'max'})
    df_lamina_day_tot['sum_dry_mass_laminea'] = df_lamina_day_tot['sum_dry_mass']
    df_lamina_day_tot['sum_dry_mass_laminea'] = df_lamina_day_tot['sum_dry_mass']
    df_RGR = df_RGR.merge(df_lamina_day_tot[['day', 'green_area', 'sum_dry_mass_laminea']], on='day')
    df_RGR['NAR_TT'] = df_RGR.delta_sum_dry_mass / df_RGR.green_area / df_RGR.delta_sum_TT

    # --- mean LAR: leaf area ratio = m2 / g DM plante
    df_RGR['LAR'] = df_RGR.green_area / df_RGR.sum_dry_mass

    # --- mean LMR: leaf mass ratio = g DM feuille / g DM plante
    df_RGR['LMR'] = df_RGR.sum_dry_mass_laminea / df_RGR.sum_dry_mass

    # --- mean SLA: m2 / g DM feuille
    df_RGR['SLA'] = df_RGR.green_area / df_RGR.sum_dry_mass_laminea

    # ---  Write results into a table
    res_df = pd.DataFrame.from_dict({'LAI': [df_LAI.loc[max(df_LAI.index), 'LAI']],
                                     'RUE_plant_MJ_PAR': [RUE_plant],
                                     'RUE_shoot_MJ_PAR': [RUE_shoot],
                                     'RUE_plant_MJ_RGint': [RUE_plant_couvert],
                                     'RUE_shoot_MJ_RGint': [RUE_shoot_couvert],
                                     'Photosynthetic_efficiency': [avg_photo_y],
                                     'C_usages_Respi_roots': C_usages_div.loc[max(C_usages_div.index), 'Respi_roots'],
                                     'C_usages_Respi_shoot': C_usages_div.loc[max(C_usages_div.index), 'Respi_shoot'],
                                     'C_usages_Respi': C_usages_div.loc[max(C_usages_div.index), 'Respi_shoot'] + C_usages_div.loc[max(C_usages_div.index), 'Respi_roots'],
                                     'C_usages_exudation': C_usages_div.loc[max(C_usages_div.index), 'exudation'],
                                     't_final': [t_end],
                                     'nb_final_em': [nb_final_em_leaves],
                                     'nb_final_lig': [nb_final_lig_leaves],
                                     'final_avg_SLA': [final_avg_SLA],
                                     'avg_phyllochron': [1 / fit_phyllo.params[1]],
                                     'avg_RGR_TT': [df_RGR.RGR_TT.mean()],
                                     'avg_RGR_shoot_TT': [df_RGR.RGR_shoot_TT.mean()],
                                     'avg_RGR_roots_TT': [df_RGR.RGR_roots_TT.mean()],
                                     'avg_NAR_TT': [df_RGR.NAR_TT.mean()],
                                     'avg_LAR': [df_RGR.LAR.mean()],
                                     'final_LAR': [df_RGR.LAR.iloc[-1]],
                                     'avg_LMR': [df_RGR.LMR.mean()],
                                     'final_LMR': [df_RGR.LMR.iloc[-1]],
                                     'avg_SLA': [df_RGR.SLA.mean()]
                                     })

    res_df.to_csv(os.path.join(scenario_postprocessing_dirpath, 'performance_indices.csv'), index=False)

# def all_scenraii_postprocessings(scenarii_list_dirpath):
#     # ------- Run the above functions for all the scenarii
#     # Import scenarii list and description
#     scenarii_df = pd.read_csv(scenarii_list_dirpath, index_col='Scenario')
#     scenarii_df['Scenario'] = scenarii_df.index
#
#     if 'Scenario_label' not in scenarii_df.keys():
#         scenarii_df['Scenario_label'] = ''
#     else:
#         scenarii_df['Scenario_label'] = scenarii_df['Scenario_label'].fillna('')
#     scenarii = scenarii_df.Scenario
#
#
#     for scenario in scenarii:
#         table_C_usages(int(scenario))
#         calculate_performance_indices(int(scenario))
