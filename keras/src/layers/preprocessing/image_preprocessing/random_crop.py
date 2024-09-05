from keras.src import backend
from keras.src.api_export import keras_export
from keras.src.layers.preprocessing.image_preprocessing.base_image_preprocessing_layer import BaseImagePreprocessingLayer
from keras.src.random.seed_generator import SeedGenerator
from keras.src.utils import image_utils


@keras_export("keras.layers.RandomCrop")
class RandomCrop(BaseImagePreprocessingLayer):
    """A preprocessing layer which randomly crops images during training.

    During training, this layer will randomly choose a location to crop images
    down to a target size. The layer will crop all the images in the same batch
    to the same cropping location.

    At inference time, and during training if an input image is smaller than the
    target size, the input will be resized and cropped so as to return the
    largest possible window in the image that matches the target aspect ratio.
    If you need to apply random cropping at inference time, set `training` to
    True when calling the layer.

    Input pixel values can be of any range (e.g. `[0., 1.)` or `[0, 255]`) and
    of integer or floating point dtype. By default, the layer will output
    floats.

    **Note:** This layer is safe to use inside a `tf.data` pipeline
    (independently of which backend you're using).

    Input shape:
        3D (unbatched) or 4D (batched) tensor with shape:
        `(..., height, width, channels)`, in `"channels_last"` format.

    Output shape:
        3D (unbatched) or 4D (batched) tensor with shape:
        `(..., target_height, target_width, channels)`.

    Args:
        height: Integer, the height of the output shape.
        width: Integer, the width of the output shape.
        seed: Integer. Used to create a random seed.
        **kwargs: Base layer keyword arguments, such as
            `name` and `dtype`.
    """

    def __init__(
        self, height, width, seed=None, data_format=None, name=None, **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.height = height
        self.width = width
        self.seed = (
            seed if seed is not None else backend.random.make_default_seed()
        )
        self.generator = SeedGenerator(seed)
        self.data_format = backend.standardize_data_format(data_format)

        if self.data_format == "channels_first":
            self.height_axis = -2
            self.width_axis = -1
        elif self.data_format == "channels_last":
            self.height_axis = -3
            self.width_axis = -2

        self.supports_masking = False
        self.supports_jit = False
        self._convert_input_args = False
        self._allow_non_tensor_positional_args = True

    def get_random_transformation(self, data, training=True, seed=None):
        if seed is None:
            seed = self._get_seed_generator(self.backend._backend)

        if isinstance(data, dict):
            input_shape = self.backend.shape(data["images"])
        else:
            input_shape = self.backend.shape(data)

        input_height, input_width = (
            input_shape[self.height_axis],
            input_shape[self.width_axis],
        )
        if input_height is None or input_width is None:
            raise ValueError(
                "RandomCrop requires the input to have a fully defined "
                f"height and width. Received: images.shape={input_shape}"
            )

        if training and input_height > self.height and input_width > self.width:
            h_start = self.backend.cast(
                self.backend.random.uniform(
                    (),
                    0,
                    maxval=float(input_height - self.height + 1),
                    seed=seed,
                ),
                "int32",
            )
            w_start = self.backend.cast(
                self.backend.random.uniform(
                    (),
                    0,
                    maxval=float(input_width - self.width + 1),
                    seed=seed,
                ),
                "int32",
            )
        else:
            crop_height = int(float(input_width * self.height) / self.width)
            crop_height = max(min(input_height, crop_height), 1)
            crop_width = int(float(input_height * self.width) / self.height)
            crop_width = max(min(input_width, crop_width), 1)
            h_start = int(float(input_height - crop_height) / 2)
            w_start = int(float(input_width - crop_width) / 2)

        return h_start, w_start

    def augment_images(self, images, transformation, training=True):
        inputs = self.backend.cast(images, self.compute_dtype)
        h_start, w_start = transformation
        if self.data_format == "channels_last":
            return self.backend.core.slice(
                inputs,
                self.backend.numpy.stack([0, h_start, w_start, 0]),
                [
                    self.backend.shape(inputs)[0],
                    self.height,
                    self.width,
                    self.backend.shape(inputs)[3],
                ],
            )
        return self.backend.core.slice(
            inputs,
            self.backend.numpy.stack([0, 0, h_start, w_start]),
            [
                self.backend.shape(inputs)[0],
                self.backend.shape(inputs)[1],
                self.height,
                self.width,
            ],
        )

    def augment_labels(self, labels, transformation, training=True):
        return labels

    def augment_bounding_boxes(self, bounding_boxes, transformation, training=True):
        """
        bounding_boxes = {
            "boxes": (batch, num_boxes, 4),  # left-top-right-bottom
            "labels": (batch, num_boxes, num_classes),
        }
        or
        bounding_boxes = {
            "boxes": (num_boxes, 4),
            "labels": (num_boxes, num_classes),
        }
        """
        boxes = bounding_boxes["boxes"]
        h_start, w_start = transformation
        # TODO: validate box format
        # TODO: convert and pad ragged, list inputs
        if len(self.backend.shape(boxes)) == 3:
            boxes = self.backend.stack(
                [
                    self.backend.maximum(boxes[:, :, 0] - h_start, 0),
                    self.backend.maximum(boxes[:, :, 1] - w_start, 0),
                    self.backend.maximum(boxes[:, :, 2] - h_start, 0),
                    self.backend.maximum(boxes[:, :, 3] - w_start, 0),
                ],
                axis=-1
            )
        else:
            boxes = self.backend.stack(
                [
                    self.backend.maximum(boxes[:, 0] - h_start, 0),
                    self.backend.maximum(boxes[:, 1] - w_start, 0),
                    self.backend.maximum(boxes[:, 2] - h_start, 0),
                    self.backend.maximum(boxes[:, 3] - w_start, 0),
                ],
                axis=-1
            )
        return {
            "boxes": boxes,
            "labels": bounding_boxes["labels"],
        }

    def augment_segmentation_masks(self, segmentation_masks, transformation, training=True):
        return self.augment_images(segmentation_masks, transformation)

    def compute_output_shape(self, input_shape, *args, **kwargs):
        input_shape = list(input_shape)
        input_shape[self.height_axis] = self.height
        input_shape[self.width_axis] = self.width
        return tuple(input_shape)

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "height": self.height,
                "width": self.width,
                "seed": self.seed,
                "data_format": self.data_format,
            }
        )
        return config