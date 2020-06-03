import numpy as np
import pandas as pd

species_table_path = "/lacie/projects1/Sam-Lapp/OPSO/resources/species_table.csv"
# print(f'reading species translations from table at {species_table_path}')

def get_species_list():
    """list of scientific-names (lowercase-hyphenated) of species in the loaded species table"""
    species_table = pd.read_csv(species_table_path)

    # create a dictionary that maps from 6 letter bn codes to xc scientific name as lowercase-hyphenated
    bn_to_xc = {}
    for i, row in species_table.iterrows():
        bn_code = row.bn_code
        xc_sci_name = row.bn_mapping_in_xc_dataset
        # if both columns have a value, make a key-value pair in dictionary
        if bn_code is not np.nan and xc_sci_name is not np.nan:
            bn_to_xc[bn_code] = xc_sci_name
    xc_species_list = list(np.sort(list(bn_to_xc.values())))

    #     print(f'loaded species table with {len(xc_species_list)} species')
    return xc_species_list


name_table = pd.read_csv(species_table_path)
name_table_sci_idx = name_table.set_index("scientific", drop=True)
name_table_com_idx = name_table.set_index("xc_common", drop=True)
name_table_bn_com_idx = name_table.set_index("bn_common", drop=True)


def sci_to_bn_common(scientific):
    return name_table_sci_idx.at[scientific, "bn_common"]

def sci_to_xc_common(scientific):
    return name_table_sci_idx.at[scientific, "xc_common"]

def common_to_sci(common):
    common = common.lower().replace(" ", "").replace("-", "")
    return name_table_com_idx.at[common, "scientific"]

def bn_common_to_sci(common):
    common = common.lower().replace(" ", "").replace("-", "")
    return name_table_bn_com_idx.at[common, "scientific"]
