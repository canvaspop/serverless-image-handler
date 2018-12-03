FROM amazonlinux:2

ENV PYCURL_SSL_LIBRARY=openssl

RUN yum update -y && \
    yum install -y yum-utils && \
    yum-config-manager --enable epel

RUN yum install -y \
    autoconf \
    automake \
    awscli \
    gcc \
    gifsicle \
    git \
    ImageMagick-devel \
    libcurl-devel \
    libjpeg-devel \
    libjpeg* \
    libpng-devel \
    libtool \
    make \
    nasm \
    openssl-devel \
    optipng \
    pngcrush \
    pngquant \
    python-devel \
    python-pip \
    wget \
    zip

RUN pip install --upgrade setuptools virtualenv

WORKDIR /tmp

RUN wget https://github.com/mozilla/mozjpeg/releases/download/v3.2/mozjpeg-3.2-release-source.tar.gz && \
    tar -zxvf mozjpeg-3.2-release-source.tar.gz && \
    cd mozjpeg  && \
    autoreconf -fiv && \
    mkdir build && cd build && \
    sh ../configure && \
    make install prefix=/var/task libdir=/var/task

WORKDIR /tmp

RUN git clone https://github.com/rflynn/imgmin.git && \
    cd imgmin && \
    autoreconf -fi && \
    ./configure && \
    make && \
    make install


# missing pngquant, gifsicle
# cp -f /usr/bin/gifsicle $VIRTUAL_ENV
# cp -f /usr/bin/pngquant $VIRTUAL_ENV
# cp -f /usr/lib64/libimagequant.so* $VIRTUAL_ENV/bin/lib

