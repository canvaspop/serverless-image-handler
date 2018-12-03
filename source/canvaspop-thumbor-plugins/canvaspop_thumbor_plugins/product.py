#!/usr/bin/python
# -*- coding: utf-8 -*-

# thumbor imaging service
# https://github.com/thumbor/thumbor/wiki

# Licensed under the MIT license:
# http://www.opensource.org/licenses/mit-license
# Copyright (c) 2011 globo.com thumbor@googlegroups.com

import os.path
import thumbor.filters
from thumbor.ext.filters import _alpha
from thumbor.filters import BaseFilter, filter_method
from thumbor.loaders import LoaderResult
from thumbor.utils import logger
from PIL import Image, ImageChops
import tornado.gen
import math
import json

#TODO: can we make the background transparent


class Filter(BaseFilter):
    regex = r'(?:product\((?P<product>.*?),(?P<sceneName>.*?)\))'
    phase = thumbor.filters.PHASE_AFTER_LOAD

    # map frames to inches
    frameDepths = {
        '075DW': 0.75,
        '150DW': 1.50,
        '250DW': 2.50
    }

    # valid range for width/height
    productRange = range(8,72)

    def on_scene_ready(self):
        {
            'PI': self.render_pillow_scene,
            'T': self.render_triptych_scene
        }[self.product]()

    def render_triptych_scene(self):
        engine = self.context.modules.engine

        parts = self.sceneName.split(',')

        # mandatory, we need a size
        if len(parts) < 2:
           logger.error('Missing width/height in scene name')
           return self.callback()

        productWidth = int(parts[0])
        productHeight = int(parts[1])

        if productWidth not in self.productRange:
            logger.error('Invalid product width (%s) rendering triptych', productWidth)
            return self.callback()

        if productHeight not in self.productRange:
            logger.error('Invalid product height (%s) rendering triptych', productHeight)
            return self.callback()

        # get edge and frame if provided
        productEdge = parts[2] if len(parts) > 2 else 'WB'
        if productEdge not in ('WB', 'BB', 'PB'):
            logger.error('Invalid edge (%s) rendering triptych', productEdge)
            productEdge = 'WB'

        productFrame = parts[3] if len(parts) > 3 else '075DW'
        if productFrame not in self.frameDepths:
            logger.error('Invalid frame (%s) rendering triptych', productFrame)
            productFrame = '075DW'

        # arbitrary max dimension of each panel
        maxDimension = 1000

        # buffer to add around the panels and between them for aesthetic purposes
        buffer = maxDimension / 20

        # the size of each panel, matching the aspect ratio of the requested product size
        ratio = float(productWidth) / float(productHeight)
        if ratio > 1:
            width = maxDimension
            height = int(maxDimension / ratio)
        else:
            height = maxDimension
            width = int(maxDimension * ratio)

        # create an image large enough to hold 3 panels with buffer around them
        scene = Image.new('RGBA', (int(3*width+4*buffer), int(height+2*buffer)))
        
        # background color for the scene
        scene.paste((255,255,255), [0,0,scene.size[0],scene.size[1]])

        # to center crop image, first calculate the size of each panel
        finalWidth = 3 * productWidth
        finalHeight = productHeight

        edgeSize = self.frameDepths[productFrame] if productEdge == 'PB' else 0.0

        image = self.engine.image.convert('RGBA')

        # (l,t,r,b) is used to center crop the image
        (w,h) = (image.size[0],image.size[1])
        (l,t,r,b) = (0,0,w,h)
        (cx,cy) = (w/2,h/2)

        # compute the ratio of the image aspect ratio to the final product aspect ratio
        aspectRatio = (float(w) / float(h)) / (float(finalWidth + 2 * edgeSize) / float(finalHeight + 2 * edgeSize))

        if aspectRatio > 1:
            # height remains same, crop width
            w /= aspectRatio
            l = int(cx - w / 2)
            r = int(cx + w / 2)
        else:
            # width remains same, crop height
            h *= aspectRatio
            t = int(cy - h / 2)
            b = int(cy + h / 2)

        # the actual center crop
        foreground = image.crop((l,t,r,b))

        # size of the edge in pixels scaled to image width (0 if not PB)
        edgeWidth = edgeSize * foreground.size[0] / (finalWidth + 2 * edgeSize)

        # size of a panel in pixels
        panelWidth = productWidth * foreground.size[0] / (finalWidth + 2 * edgeSize)
        panelHeight = productHeight * foreground.size[1] / (finalHeight + 2 * edgeSize)

        cropBox = (edgeWidth, edgeWidth, edgeWidth + panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width,height))
        pasteBox = (buffer, buffer, width+buffer, height+buffer)
        scene.paste(panel, pasteBox)

        cropBox = (cropBox[2], edgeWidth, cropBox[2]+panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width,height))
        pasteBox = (pasteBox[2]+buffer, buffer, pasteBox[2]+width+buffer, height+buffer)
        scene.paste(panel, pasteBox)

        cropBox = (cropBox[2], edgeWidth, cropBox[2]+panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width,height))
        pasteBox = (pasteBox[2]+buffer, buffer, pasteBox[2]+width+buffer, height+buffer)
        scene.paste(panel, pasteBox)

        self.engine.image = scene
        self.callback()

    def warp_panel(self, panel, a=50):
        (w,h) = panel.size
        image = Image.new('RGBA', (w, h+(2*a)))
        image.paste((255,255,255), [0,0,image.size[0],image.size[1]])
        image.paste(panel, (0, a) )

        return image.transform((w, h), Image.QUAD, (0,a, 0, h+a, w,h+(2*a), w,0), Image.BILINEAR)

    def render_pillow_scene(self):

        base = os.path.dirname(__file__)
        
        # resizeWidth is a magic number but is calculatable as follows:
        #
        # resizeWidth = maskArea * 19.5 / 18
        #
        # where:
        # - maskArea is the size of the mask inside the scene (approximately 900 x 900 for pillows)
        # - 19.5 is the size (in inches) of the generated print image for pillows
        # - 18 is the finished size (in inches) of the pillow
        
        scenes = {
        'PI' : {'1' : {'scene' : os.path.join(base, 'scenes/pillow-1.jpg'),
                       'mask' : os.path.join(base, 'scenes/pillow-1.png'),
                       'resizeWidth': 975},
                }
        }

        scene = scenes.get(self.product).get(self.sceneName).get('scene')
        mask =  scenes.get(self.product).get(self.sceneName).get('mask')
        
        #see note above on resizeWidth
        minwidth = scenes.get(self.product).get(self.sceneName).get('resizeWidth')

        scene = Image.open(scene).convert('RGBA')

        foreground = self.engine.image.convert('RGBA')

        wpercent = (minwidth/float(foreground.size[0]))
        hsize = int((float(foreground.size[1])*float(wpercent)))
        foreground = foreground.resize((minwidth,hsize), Image.BILINEAR)

        ## Create a masked version of the source image
        ## May want to do this post transform
        mask = Image.open(mask).convert('RGBA')

        img_w, img_h = foreground.size
        bg_w, bg_h = scene.size
        offset = ((bg_w - img_w) / 2, (bg_h - img_h) / 2)

        ## Make new image size of scene
        c1 = Image.new("RGBA",scene.size)
        c1.paste(foreground, offset)

        c2 = Image.new("RGBA",scene.size)
        c2.paste(c1, (0,0), mask)

        out = ImageChops.multiply(scene, c1)
        composite = Image.composite(out, scene, mask)
        self.engine.image = composite 

        # all done
        self.callback()


    @filter_method(
       BaseFilter.String,
       r'(.*?)',
       async=True
    )

    @tornado.gen.coroutine
    def product(self, callback, product, sceneName):
        self.product = product
        self.sceneName = sceneName
        self.callback = callback

        self.on_scene_ready()