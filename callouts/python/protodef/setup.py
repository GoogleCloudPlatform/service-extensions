from distutils.core import setup
import glob

package_list = ['envoy', 'udpa', 'validate', 'xds']
glob_list = [glob.glob(f'{glob_dir}/**/', recursive=True) for glob_dir in package_list]
for glob_dirs in glob_list:
    package_list += glob_dirs
setup(name='protodef', version='1.0.0', packages=package_list)