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
from PIL import Image, ImageChops, ImageDraw, ImageFilter
import tornado.gen
import math
import json

class Filter(BaseFilter):
    regex = r'(?:product\((?P<product>.*?),(?P<sceneName>.*?)\))'
    phase = thumbor.filters.PHASE_AFTER_LOAD

    # map frames to inches
    frameDepths = {
        '075DW': 0.75,
        '150DW': 1.50,
        '250DW': 2.50,
        'EF': 1.50,
        'WF': 1.50,
        'BF': 1.50,
    }

    # valid range for width/height
    canvasProductRange = [8, 72]

    def on_scene_ready(self):
        {
            'PI': self.render_pillow_scene,
            'T': self.render_triptych_scene,
            'S': self.render_single_scene,
            'FP': self.render_framed_scene,
            'SPP': self.render_pet_portrait_scene
        }[self.product]()

    def render_single_scene(self):
        engine = self.context.modules.engine
        parts = self.sceneName.split(',')

        # mandatory, we need a size
        if len(parts) < 2:
           logger.error('Missing width/height in scene name')
           return self.callback()

        productWidth = float(parts[0])
        productHeight = float(parts[1])

        if productWidth < self.canvasProductRange[0] or productWidth > self.canvasProductRange[1]:
            logger.error('Invalid product width (%s) rendering single', productWidth)
            return self.callback()

        if productHeight < self.canvasProductRange[0] or productHeight > self.canvasProductRange[1]:
            logger.error('Invalid product height (%s) rendering single', productHeight)
            return self.callback()

        # get edge and frame if provided
        productEdge = parts[2] if len(parts) > 2 else 'WB'
        if productEdge not in ('WB', 'BB', 'PB'):
            logger.error('Invalid edge (%s) rendering single', productEdge)
            productEdge = 'WB'

        productFrame = parts[3] if len(parts) > 3 else '075DW'
        if productFrame not in self.frameDepths:
            logger.error('Invalid frame (%s) rendering single', productFrame)
            productFrame = '075DW'

        if productFrame in ('WF','EF','BF'):
            return self.render_framed_scene('S')

        # version 2 is for printables
        version = int(parts[4]) if len(parts) > 4 else 1

        logger.debug('Rendering single with version %s', version)

        # arbitrary max dimension of each panel
        maxDimension = 1000

        # buffer to add around the panels and between them for aesthetic purposes
        buffer = maxDimension / 20

        # in version 2 the image contains the frame
        if version == 2:
            productWidth += 2 * self.frameDepths[productFrame]
            productHeight += 2 * self.frameDepths[productFrame]

        # the size of each panel, matching the aspect ratio of the requested product size
        ratio = float(productWidth) / float(productHeight)
        if ratio > 1:
            width = maxDimension
            height = int(maxDimension / ratio)
        else:
            height = maxDimension
            width = int(maxDimension * ratio)

        # create an image with buffer around them
        scene = Image.new('RGBA', (int(width+2*buffer), int(height+2*buffer)), (255,255,255,0))

        finalWidth = productWidth
        finalHeight = productHeight

        edgeSize = self.frameDepths[productFrame] if productEdge == 'PB' and version == 1 else 0.0

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

        logger.debug('initial crop is %s', (l,t,r,b))

        # the actual center crop
        foreground = image.crop((l,t,r,b))

        # if version = 2 then this is a printable that includes the border so we need to
        # crop the borders off by the edge size first (this accommodates PB)
        if version == 2:
            frameSize = self.frameDepths[productFrame] * 2.0
            crop = foreground.size[0] * (frameSize / productWidth) / 2.0
            logger.debug('crop size is %s', crop)
            foreground = foreground.crop((crop, crop, foreground.size[0]-crop, foreground.size[1]-crop))

        # size of the edge in pixels scaled to image width (0 if not PB)
        edgeWidth = edgeSize * foreground.size[0] / (finalWidth + 2 * edgeSize)

        # size of a panel in pixels
        panelWidth = productWidth * foreground.size[0] / (finalWidth + 2 * edgeSize)
        panelHeight = productHeight * foreground.size[1] / (finalHeight + 2 * edgeSize)

        cropBox = (edgeWidth, edgeWidth, edgeWidth + panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width,height))

        # frame shadow
        frameShadow = ImageDraw.Draw(scene, 'RGBA')
        frameShadow.rectangle([(buffer+10, buffer+20), (buffer+panel.size[0]-10, buffer+panel.size[1]+20)], (20,20,20,140))
        scene = scene.filter(ImageFilter.GaussianBlur(20))

        pasteBox = (buffer, buffer, width+buffer, height+buffer)
        scene.paste(panel, pasteBox)

        self.engine.image = scene
        self.callback()

    def render_framed_scene(self, type = 'FP'):
        engine = self.context.modules.engine
        parts = self.sceneName.split(',')
        # map matte options to inches
        edgeOptions = {
            'NOMA': 0,
            '250MA': 2.5,
            'BB': 0.1,
            'WB': 0.1
        }

        frameColors = {
            'BF': (50, 50, 50),
            'WF': (230, 230, 230),
            'EF': (100, 87, 72)
        }

        shineColors = {
            'BF': (20, 20, 20),
            'WF': (255, 255, 255),
            'EF': (60, 48, 30)
        }

        outlineColors = {
            'BF': (120,120,120),
            'WF': (200,200,200),
            'EF': (100, 87, 72)
        }

        if type == 'FP':
            framedProductRange = [8, 53]
        else:
            framedProductRange = self.canvasProductRange

        # mandatory, we need a size
        if len(parts) < 2:
            logger.error('Missing width/height in scene name')
            return self.callback()
        productWidth = int(parts[0])
        productHeight = int(parts[1])
        if productWidth < framedProductRange[0] or productWidth > framedProductRange[1]:
            logger.error('Invalid product width (%s) rendering framed', productWidth)
            return self.callback()
        if productHeight < framedProductRange[0] or productHeight > framedProductRange[1]:
            logger.error('Invalid product height (%s) rendering framed', productHeight)
            return self.callback()

        # get edge and frame if provided
        productEdge = parts[2] if len(parts) > 2 else 'NOMA'
        if productEdge not in edgeOptions:
            logger.error('Invalid edge (%s) rendering framed', productEdge)
            productEdge = 'NOMA'
        productFrame = parts[3] if len(parts) > 3 else 'BF'
        if productFrame not in frameColors:
            logger.error('Invalid frame (%s) rendering framed', productFrame)
            productFrame = 'BF'
        strokeLength = 1
        if type == 'FP':
            matteColor = (255, 255, 253, 255)
        else:
            matteColor = (0, 0, 0, 255)
        frameColor = frameColors[productFrame]
        outlineColor = outlineColors[productFrame]
        shadeColor = (200,200,200)
        shadowColor = (20,20,20,35)

        # version 2 is for printables
        version = int(parts[4]) if len(parts) > 4 else 1

        if type == 'S' and version == 2:
            logger.debug('adjusting product size for framed single panel')
            productWidth += 2 * self.frameDepths[productFrame]
            productHeight += 2 * self.frameDepths[productFrame]

        finishedWidth = productWidth + 2*(0.75 + edgeOptions[productEdge])
        finishedHeight = productHeight + 2*(0.75 + edgeOptions[productEdge])

        # arbitrary max dimension
        maxDimension = 1280

        # buffer to add around the panels and between them for aesthetic purposes
        buffer = maxDimension / 15

        # the size of the frame matching the aspect ratio of the requested product size
        ratio = float(finishedWidth) / float(finishedHeight)
        if ratio > 1:
            width = maxDimension
            height = int(maxDimension / ratio)
        else:
            height = maxDimension
            width = int(maxDimension * ratio)

        # create an image with a buffer around it
        scene = Image.new('RGBA', (int(width + (2*buffer)), int(height + (2*buffer))), (255,255,255,0))
        dpi = (scene.size[0] - (2 * buffer)) / finishedWidth
        matteLength = math.ceil(edgeOptions[productEdge] * dpi) #in pixels scaled to size of image
        frameLength = math.ceil(0.75 * dpi)
        outerFramePosStart = (buffer, buffer)
        outerFramePosEnd = (int(scene.size[0] - buffer), int(scene.size[1] - buffer))
        innerFramePosStart = (int(outerFramePosStart[0] + frameLength), int(outerFramePosStart[1] + frameLength))
        innerFramePosEnd = (int(outerFramePosEnd[0] - frameLength), int(outerFramePosEnd[1] - frameLength))
        mattePosStart = (int(innerFramePosStart[0]), int(innerFramePosStart[1]))
        mattePosEnd = (int(innerFramePosEnd[0]), int(innerFramePosEnd[1]))
        imagePosStart = (int(mattePosStart[0] + matteLength), int(mattePosStart[1] + matteLength))
        imagePosEnd = (int(mattePosEnd[0] - matteLength), int(mattePosEnd[1] - matteLength))

        # amount in inches to crop off the matte extension which cuts into the actual image
        edgeSize = (0.125 * dpi) if productEdge == '250MA' else 0.0

        image = self.engine.image.convert('RGBA')

        # (x0,y0,x1,y1) is used to center crop the image
        (w, h) = (image.size[0], image.size[1])
        (x0, y0, x1, y1) = (0, 0, w, h)
        (cx, cy) = (w/2, h/2)

        # compute the ratio of the image aspect ratio to the final product aspect ratio
        aspectRatio = (float(w) / float(h)) / (float(imagePosEnd[0] - imagePosStart[0] + (2 * edgeSize)) / float(imagePosEnd[1] - imagePosStart[1] + (2 * edgeSize)))
        if aspectRatio > 1:
            # height remains same, crop width
            w /= aspectRatio
            x0 = int(cx - w / 2)
            x1 = int(cx + w / 2)
        else:
            # width remains same, crop height
            h *= aspectRatio
            y0 = int(cy - h / 2)
            y1 = int(cy + h / 2)

        # the actual center crop
        foreground = image.crop((x0, y0, x1, y1))
        # if version = 2 then this is a printable that includes the border so we need to
        # crop the borders off by the edge size first (this accommodates PB)
        if version == 2 and type == 'S':
            frameSize = self.frameDepths[productFrame] * 2.0
            crop = foreground.size[0] * (frameSize / productWidth) / 2.0
            logger.debug('crop size is %s', crop)
            foreground = foreground.crop((crop, crop, foreground.size[0]-crop, foreground.size[1]-crop))

        foreground = foreground.crop((edgeSize, edgeSize, foreground.size[0] - edgeSize, foreground.size[1] - edgeSize))
        panel = foreground.resize((imagePosEnd[0] - imagePosStart[0] + 1, imagePosEnd[1] - imagePosStart[1] + 1)) #+1 because it seems to not cover the entire area and leaves a blank 1x1 row and column at the right and bottom. Might be due to resize artifact?

        # frame shadow
        frameShadow = ImageDraw.Draw(scene, 'RGBA')
        frameShadow.rectangle([(outerFramePosStart[0]+10, outerFramePosStart[1]+20), (outerFramePosEnd[0]-10, outerFramePosEnd[1]+20)], (20,20,20,140))
        scene = scene.filter(ImageFilter.GaussianBlur(20))

        #outer frame
        outerFrame = ImageDraw.Draw(scene, 'RGBA')
        outerFrame.rectangle([outerFramePosStart, outerFramePosEnd], frameColor, outlineColor, strokeLength)

        # 3d effect on frame
        overlay = Image.new('RGBA', (int(scene.size[0]), int(scene.size[1])), (255,255,255,0))
        shineEffect = ImageDraw.Draw(overlay, 'RGBA')
        shineEffect.rectangle([(outerFramePosStart[0] + 1, outerFramePosStart[1] + 1), (outerFramePosEnd[0] - 1, outerFramePosEnd[1] - 1)], shineColors[productFrame])
        overlay = overlay.filter(ImageFilter.GaussianBlur(2))
        scene.paste(overlay, (0,0), overlay)

        # frame trim
        frameTrim = ImageDraw.Draw(scene, 'RGBA')
        #top left
        frameTrim.line([(outerFramePosStart[0], outerFramePosStart[1]), (innerFramePosStart[0], innerFramePosStart[1])], outlineColor, strokeLength)
        #bottom left
        frameTrim.line([(outerFramePosStart[0], outerFramePosEnd[1]), (innerFramePosStart[0], innerFramePosEnd[1])], outlineColor, strokeLength)
        # top right
        frameTrim.line([(innerFramePosEnd[0], innerFramePosStart[1]), (outerFramePosEnd[0], outerFramePosStart[1])], outlineColor, strokeLength)
        # bottom right
        frameTrim.line([(innerFramePosEnd[0], innerFramePosEnd[1]), (outerFramePosEnd[0], outerFramePosEnd[1])], outlineColor, strokeLength)

        # matte
        matte = ImageDraw.Draw(scene, 'RGBA')
        matte.rectangle([mattePosStart, mattePosEnd], matteColor)

        scene.paste(panel, imagePosStart)

        # shadows inner frame
        overlay = Image.new('RGBA', (int(scene.size[0]), int(scene.size[1])), (255,255,255,0))
        innerFrameShadow = ImageDraw.Draw(overlay, 'RGBA')
        shadowCastLength = 10
        innerFrameShadow.rectangle([(innerFramePosStart[0] - 3, innerFramePosStart[1] - 3), (innerFramePosStart[0] + shadowCastLength, innerFramePosEnd[1] + 3)], shadowColor)
        innerFrameShadow.rectangle([(innerFramePosStart[0] - 3 + shadowCastLength, innerFramePosStart[1]-3), (innerFramePosEnd[0] + 3, innerFramePosStart[1] + shadowCastLength)], shadowColor)
        innerFrameShadow.rectangle([(innerFramePosStart[0] - 3 + shadowCastLength, innerFramePosEnd[1]-6), (innerFramePosEnd[0] + 3, innerFramePosEnd[1]+3)], shadowColor)
        innerFrameShadow.rectangle([(innerFramePosEnd[0] - 6, innerFramePosStart[1] -3 + shadowCastLength), (innerFramePosEnd[0] + 3, innerFramePosEnd[1] - 6)], shadowColor)
        overlay = overlay.filter(ImageFilter.GaussianBlur(5))
        scene.paste(overlay, (0,0), overlay)

        # inner frame
        innerFrame = ImageDraw.Draw(scene, 'RGBA')
        innerFrame.rectangle([innerFramePosStart, innerFramePosEnd], None, outlineColor, 1)

        # matte inner emboss
        if (matteLength > 0 and type == 'FP'):
            shadeImageFrame = ImageDraw.Draw(scene, 'RGBA')
            shadeImageFrame.rectangle([(imagePosStart[0]-5, imagePosStart[1]-5), (imagePosEnd[0]+5, imagePosEnd[1] +5)], None, shadeColor, int(5))

        self.engine.image = scene
        self.callback()

    def render_pet_portrait_scene(self):
        engine = self.context.modules.engine

        image = self.engine.image.convert('RGBA')

        # (l,t,r,b) is used to center crop the image
        (w,h) = (image.size[0],image.size[1])
        (l,t,r,b) = (37,37,w-37,h-37)

        # the actual center crop
        foreground = image.crop((l,t,r,b))

        self.engine.image = foreground
        self.render_single_scene()


    def render_triptych_scene(self):
        engine = self.context.modules.engine

        parts = self.sceneName.split(',')

        # mandatory, we need a size
        if len(parts) < 2:
            logger.error('Missing width/height in scene name')
            return self.callback()

        productWidth = int(parts[0])
        productHeight = int(parts[1])

        if productWidth < self.canvasProductRange[0] or productWidth > self.canvasProductRange[1]:
            logger.error('Invalid product width (%s) rendering triptych', productWidth)
            return self.callback()

        if productHeight < self.canvasProductRange[0] or productHeight > self.canvasProductRange[1]:
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
        scene = Image.new('RGBA', (int(3*width+4*buffer), int(height+2*buffer)), (255,255,255,0))

        # to center crop image, first calculate the size of each panel
        finalWidth = 3 * productWidth
        finalHeight = productHeight

        edgeSize = self.frameDepths[productFrame] if productEdge == 'PB' else 0.0

        image = self.engine.image.convert('RGBA')

        # (l,t,r,b) is used to center crop the image
        (w, h) = (image.size[0], image.size[1])
        (l, t, r, b) = (0, 0, w, h)
        (cx, cy) = (w/2, h/2)

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
        foreground = image.crop((l, t, r, b))

        # size of the edge in pixels scaled to image width (0 if not PB)
        edgeWidth = edgeSize * foreground.size[0] / (finalWidth + 2 * edgeSize)

        # size of a panel in pixels
        panelWidth = productWidth * foreground.size[0] / (finalWidth + 2 * edgeSize)
        panelHeight = productHeight * foreground.size[1] / (finalHeight + 2 * edgeSize)

        cropBox = (edgeWidth, edgeWidth, edgeWidth + panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width, height))
        pasteBox = (buffer, buffer, width+buffer, height+buffer)
        # frame shadow
        overlay = Image.new('RGBA', (int(3*width+4*buffer), int(height+2*buffer)), (255,255,255,0))
        frameShadow = ImageDraw.Draw(overlay, 'RGBA')
        frameShadow.rectangle([(buffer+10, buffer+25), (buffer+width-10, buffer+height+25)], (20,20,20,200))
        overlay = overlay.filter(ImageFilter.GaussianBlur(15))
        scene.paste(overlay, (0,0), overlay)
        scene.paste(panel, pasteBox)

        cropBox = (cropBox[2], edgeWidth, cropBox[2] + panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width, height))
        pasteBox = (pasteBox[2]+buffer, buffer, pasteBox[2]+width+buffer, height+buffer)
        # frame shadow
        overlay = Image.new('RGBA', (int(3*width+4*buffer), int(height+2*buffer)), (255,255,255,0))
        frameShadow = ImageDraw.Draw(overlay, 'RGBA')
        frameShadow.rectangle([(pasteBox[0]+10, buffer+25), (pasteBox[2]-10, buffer+height+25)], (20,20,20,200))
        overlay = overlay.filter(ImageFilter.GaussianBlur(15))
        scene.paste(overlay, (0,0), overlay)
        scene.paste(panel, pasteBox)

        cropBox = (cropBox[2], edgeWidth, cropBox[2] + panelWidth, edgeWidth + panelHeight)
        panel = foreground.crop(cropBox).resize((width, height))
        pasteBox = (pasteBox[2]+buffer, buffer, pasteBox[2]+width+buffer, height+buffer)
        # frame shadow
        overlay = Image.new('RGBA', (int(3*width+4*buffer), int(height+2*buffer)), (255,255,255,0))
        frameShadow = ImageDraw.Draw(overlay, 'RGBA')
        frameShadow.rectangle([(pasteBox[0]+10, buffer+25), (pasteBox[2]-10, buffer+height+25)], (20,20,20,200))
        overlay = overlay.filter(ImageFilter.GaussianBlur(15))
        scene.paste(overlay, (0,0), overlay)
        scene.paste(panel, pasteBox)

        self.engine.image = scene
        self.callback()

    def warp_panel(self, panel, a=50):
        (w, h) = panel.size
        image = Image.new('RGBA', (w, h+(2*a)))
        image.paste((255, 255, 255), [0, 0, image.size[0], image.size[1]])
        image.paste(panel, (0, a))

        return image.transform((w, h), Image.QUAD, (0, a, 0, h+a, w, h+(2*a), w, 0), Image.BILINEAR)

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
            'PI': {'1': {'scene': os.path.join(base, 'scenes/pillow-1.png'),
                         'mask': os.path.join(base, 'scenes/pillow-1.png'),
                         'shadow': os.path.join(base, 'scenes/pillow-1-shadow.png'),
                         'resizeWidth': 975},
                   }
        }

        scene = scenes.get(self.product).get(self.sceneName).get('scene')
        mask = scenes.get(self.product).get(self.sceneName).get('mask')
        shadow = scenes.get(self.product).get(self.sceneName).get('shadow')

        # see note above on resizeWidth
        minwidth = scenes.get(self.product).get(self.sceneName).get('resizeWidth')

        scene = Image.open(scene).convert('RGBA')

        foreground = self.engine.image.convert('RGBA')

        wpercent = (minwidth/float(foreground.size[0]))
        hsize = int((float(foreground.size[1])*float(wpercent)))
        foreground = foreground.resize((minwidth, hsize), Image.BILINEAR)

        # Create a masked version of the source image
        # May want to do this post transform
        mask = Image.open(mask).convert('RGBA')

        img_w, img_h = foreground.size
        bg_w, bg_h = scene.size
        offset = ((bg_w - img_w) / 2, (bg_h - img_h) / 2)

        shadowScene = Image.new('RGBA', scene.size, (255,255,255,0))
        maskShadow = Image.open(shadow).convert('RGBA')
        shadowScene.paste(maskShadow, (0,0), maskShadow)
        
        # Make new image size of scene
        c1 = Image.new("RGBA", scene.size, (255,255,255,255))
        c1.paste(foreground, offset)
        c2 = Image.new("RGBA", scene.size)
        c2.paste(c1, (0, 0), mask)
        out = ImageChops.multiply(scene, c1)
        composite = Image.composite(out, scene, mask)        

        scene.paste(shadowScene, (0,0))
        scene.paste(composite, (0,0), mask)

        self.engine.image = scene

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
