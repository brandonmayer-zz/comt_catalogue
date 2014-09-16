from owslib import fes, csw

from netCDF4 import Dataset as ncDataset
from netCDF4 import num2date, date2num

import pyugrid
import numpy as np


endpoint = "http://www.ngdc.noaa.gov/geoportal/csw"
uuid = '8BF00750-66C7-49FF-8894-4D4F96FD86C0'
uuid_filter = fes.PropertyIsEqualTo(propertyname='sys.siteuuid', literal="{{{0}}}".format(uuid))
timeout = 120

map = {
   'time': {'standard_name':'time'},
   'longitude': {'standard_name':'longitude', 'scale_min':'0', 'scale_max':'360'},
   'latitude': {'standard_name':'latitude', 'scale_min':'-90', 'scale_max':'90'},
   'ssh_geoid': {'standard_name':'sea_surface_height_above_geoid', 'scale_min':'0', 'scale_max':'7.0'},
   'ssh_reference_datum': {'standard_name':'water_surface_height_above_reference_datum', 'scale_min':'0', 'scale_max':'7.0'},
   'u': {'standard_name':'eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'v': {'standard_name':'northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'hs': {'standard_name':'sea_surface_wave_significant_height', 'scale_min':'0', 'scale_max':'12'},
   'uwind': {'standard_name':'eastward_wind', 'scale_min':'0', 'scale_max':'80'},
   'vwind': {'standard_name':'northward_wind', 'scale_min':'0', 'scale_max':'80'},
   'salinity': {'standard_name':'sea_water_salinity', 'scale_min':'32', 'scale_max':'37'},
   'sst': {'standard_name':'sea_water_temperature', 'scale_min':'0', 'scale_max':'40'},
   'ubarotropic': {'standard_name':'barotropic_eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'vbarotropic': {'standard_name':'barotropic_northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
}

def get_by_standard_name(nc, standard_name):
    for vn, v in nc.variables.iteritems():
        # sn - standard_name
        sn = nc.variables[vn].__dict__.get('standard_name', None)
        if sn == None:
            continue
        # cm - cell_methods
        cm = nc.variables[vn].__dict__.get('cell_methods', None)
        # if cell_method specified, prepend method to key
        if cm != None:
            cm = re.sub(":\s+", "_", cm)
            cm = re.sub("\s+", "", cm)
            sn = '%s_%s' % (cm, sn)
        if sn == standard_name:
            return v
    return None

def nc_name_from_standard(nc, standard_name):
    """
    Reverse lookup from standard name to nc name.
    """
    ret = None
    for k, v in nc.variables.iteritems():
        if standard_name == v.__dict__.get('standard_name'):
            ret = k
            break
    return ret
            
def get_global_attribute(nc, attr):
    """
    Wrapper to return None if attr DNE.
    attr is a string
    """
    try:
        ret = getattr(nc,attr)
    except:
        ret = None
    return ret

def get_spatial_extent(nc, legal_name):
    try:
        if 'lat' and 'lon' in nc.variables:
            lon = nc.variables['lon'][:]
            lat = nc.variables['lat'][:]
        elif 'x' and 'y' in nc.variables:
            lon = nc.variables['x'][:]
            lat = nc.variables['y'][:]
        elif 'lat_u' and 'lon_u' in nc.variables:
            lon = nc.variables['lon_u'][:]
            lat = nc.variables['lat_u'][:]
        elif 'lat_v' and 'lon_v' in nc.variables:
            lon = nc.variables['lon_v'][:]
            lat = nc.variables['lat_v'][:]
        else:
            logger.info("Couldn't Compute Spatial Extent {0}".format(legal_name))
            return []

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " +
                     repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        return []
    
    return [np.nanmin(lon), np.nanmin(lat), np.nanmax(lon), np.nanmax(lat)]
    
def get_temporal_extent(nc,time_var_name='time'):
    temp_ext = []
    
    # tobj = nc.variables.get(time_var_name)
    tobj = get_by_standard_name(nc, 'time')
    if tobj:
        tkwargs = {}
        if hasattr(tobj, 'units'):
            tkwargs['units'] = tobj.units
        if hasattr(tobj, 'calendar'):
            tkwargs['calendar'] = tobj.calendar.lower()

        times = tobj[:]
        dates = []
        for t in times:
            try:
                dates.append(num2date(t, **tkwargs))
            except:
                pass

        if len(dates):
            temp_ext = [dates[0], dates[-1]]

    return temp_ext

def get_layers(nc, vars=['depth','u,v']):

    '''
    BM: updating 20140801 to use UI names defined in sciwms/util/cf
        only variables with CF compliant standard_name can be added
    '''

    # return dict: key is UI displayable name (eg. shown in badges), value is default style for this layer
    layers = {}

    # disabling auto-scaling by requireing min/max values
    default_scalar_plot = "pcolor_average_jet_%s_%s_grid_False"
    default_vector_plot = "vectors_average_jet_%s_%s_grid_40"
    
    nc_id = get_global_attribute(nc,'id')
    nc_model = get_global_attribute(nc,'model')
    print 'nc_id = {0}'.format(nc_id)
    print 'nc_model = {0}'.format(nc_model)

    # going to loop through the variables in NetCDF object, if standard_name exists and is in util/cf map, add, else, ignore
    for variable_name, variable in nc.variables.iteritems():
        # standard_name
        standard_name = nc.variables[variable_name].__dict__.get('standard_name', None)
        if standard_name == None:
            continue
        print 'variable name = {0}, standard name = {1}'.format(variable_name, standard_name)
        # cell_methods (standard_name is not always unique in Dataset)
        cell_methods = nc.variables[variable_name].__dict__.get('cell_methods', None)
        # if cell_method specified, prepend cell_method to standard_name for uniqueness
        if cell_methods != None:
            cell_methods = re.sub(":\s+", "_", cell_methods)
            cell_methods = re.sub("\s+", "", cell_methods)
            standard_name = '%s_%s' % (cell_methods, standard_name)
        # is this standard_name in the cf.map?
        for k,v in cf.map.items():
            # if standard_name is in map, add to layers dict with style as value
            if v['standard_name'] == standard_name:
                scale_min = v.get('scale_min', None)
                scale_max = v.get('scale_max', None)
                style = default_scalar_plot % (scale_min, scale_max)
                logger.info('adding %s with LAYER name %s and default STYLE %s' % (standard_name, k, style))
                print 'adding %s with LAYER name %s and default STYLE %s' % (standard_name, k, style)
                layers[k] = style

    # ---------------------------
    # HACK SECTION
    # ---------------------------
    # if combine vector fields TODO: hack, whats a good way to do this?
    if 'u' in layers and 'v' in layers:
        layers['u,v'] = 'vectors_average_jet_0_2_grid_40' #TODO use scale_min/scale_max
        del layers['u']
        del layers['v']
    if 'uwind' in layers and 'vwind' in layers:
        layers['uwind,vwind'] = 'vectors_average_jet_0_50_grid_40' #TODO use scale_min/scale_max
        del layers['uwind']
        del layers['vwind']
    if 'ubarotropic' in layers and 'vbarotropic' in layers:
        layers['ubarotropic,vbarotropic'] = 'vectors_average_jet_0_2_grid_40' #TODO use scale_min/scale_max
        del layers['ubarotropic']
        del layers['vbarotropic']

    # no time, latitude, longitude passed back TODO: hack
    layers.pop('time', None)
    layers.pop('latitude', None)
    layers.pop('longitude', None)

    print layers.keys()

    return layers


