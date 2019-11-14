#!/bin/bash

# Build source
echo "Staring to build distribution"
echo "export deployment_dir=`pwd`"
export deployment_dir=`pwd`
echo "mkdir -p dist"
mkdir -p dist
cd $deployment_dir/dist
pwd
echo "virtualenv env"
virtualenv env
echo "source env/bin/activate"
source env/bin/activate
cd ../../source
pwd
echo "install old pip"
pip install pip==9.0.3
echo "pip install source/image-handler/. --target=$VIRTUAL_ENV/lib/python2.7/site-packages/"
pip install image-handler/. --target=$VIRTUAL_ENV/lib/python2.7/site-packages/
echo "pip install -r source/image-handler/requirements.txt --target=$VIRTUAL_ENV/lib/python2.7/site-packages/"
pip install -r image-handler/requirements.txt --target=$VIRTUAL_ENV/lib/python2.7/site-packages/
echo "pip install -r source/requirements.txt --target=$VIRTUAL_ENV/lib/python2.7/site-packages/"
pip install -r requirements.txt --target=$VIRTUAL_ENV/lib/python2.7/site-packages/
# we have to manually install 5.3 because thumbor-plugins forces 5.2 installation.
echo "pip uninstall Pillow"
pip uninstall -y Pillow
echo "pip install Pillow==5.3.0"
pip install Pillow==5.3.0

cd $VIRTUAL_ENV
cp -f /usr/bin/jpegtran $VIRTUAL_ENV
cp -f /usr/bin/optipng $VIRTUAL_ENV
cp -f /usr/bin/pngcrush $VIRTUAL_ENV
cp -f /usr/bin/pngquant $VIRTUAL_ENV
cp -f "/usr/local/bin/imgmin" $VIRTUAL_ENV

mkdir $VIRTUAL_ENV/bin/lib
cp -f /var/task/libjpeg.so* $VIRTUAL_ENV/bin/lib
cp -f /var/task/bin/jpegtran $VIRTUAL_ENV/mozjpeg
cp -f /usr/lib64/libpng15.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/liblcms2.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libm.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libz.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libgcc_s.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libpthread.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libdl.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libc.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libMagickWand.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libMagickCore.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libgomp.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libtiff.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libXt.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libltdl.so* $VIRTUAL_ENV/bin/lib
cp -f /usr/lib64/libjbig.so* $VIRTUAL_ENV/bin/lib
cp -f /lib64/libimagequant.so* $VIRTUAL_ENV/bin/lib

#packing all
cd $VIRTUAL_ENV/lib/python2.7/site-packages
pwd
echo "zip -q -r9 $VIRTUAL_ENV/../serverless-image-handler.zip *"
zip -q -r9 $VIRTUAL_ENV/../serverless-image-handler.zip *
cd $VIRTUAL_ENV
pwd
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip jpegtran"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip jpegtran
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip optipng"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip optipng
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip pngcrush"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip pngcrush
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip pngquant"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip pngquant
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip mozjpeg"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip mozjpeg
echo "zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip imgmin"
zip -q -g $VIRTUAL_ENV/../serverless-image-handler.zip imgmin
cd $VIRTUAL_ENV/bin
pwd
echo "zip -r -q -g $VIRTUAL_ENV/../serverless-image-handler.zip lib"
zip -r -q -g $VIRTUAL_ENV/../serverless-image-handler.zip lib
cd $VIRTUAL_ENV
pwd
cd ..
zip -q -d serverless-image-handler.zip pip*
zip -q -d serverless-image-handler.zip easy*
echo "Clean up build material"
rm -rf $VIRTUAL_ENV
echo "Completed building distribution"

