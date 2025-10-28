# [CavaFace: Comprehensive facial analysis by extracting face features](#)

A PyTorch-based framework for training face recognition models that generates facial embeddings for verification and identification tasks

This is based on the implementation of CavaFace found [here](https://github.com/cavalleria/cavaface). This repository contains scripts for optimized on-device
export suitable to run on Qualcomm® devices. More details on model performance
accross various devices, can be found [here](https://aihub.qualcomm.com/models/cavaface).

[Sign up](https://myaccount.qualcomm.com/signup) to start using Qualcomm AI Hub and run these models on a hosted Qualcomm® device.




## Example & Usage

Install the package via pip:
```bash
pip install "qai-hub-models[cavaface]"
```


Once installed, run the following simple CLI demo on the host machine:

```bash
python -m qai_hub_models.models.cavaface.demo
```
More details on the CLI tool can be found with the `--help` option. See
[demo.py](demo.py) for sample usage of the model including pre/post processing
scripts. Please refer to our [general instructions on using
models](../../../#getting-started) for more usage instructions.

## Export for on-device deployment

This package contains export scripts that produce a model optimized for
on-device deployment. This can be run as follows:

```bash
python -m qai_hub_models.models.cavaface.export
```
Additional options are documented with the `--help` option.


## License
* The license for the original implementation of CavaFace can be found
  [here](https://github.com/cavalleria/cavaface/blob/master/LICENSE).
* The license for the compiled assets for on-device deployment can be found [here](https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/Qualcomm+AI+Hub+Proprietary+License.pdf)


## References
* [Source Model Implementation](https://github.com/cavalleria/cavaface)



## Community
* Join [our AI Hub Slack community](https://aihub.qualcomm.com/community/slack) to collaborate, post questions and learn more about on-device AI.
* For questions or feedback please [reach out to us](mailto:ai-hub-support@qti.qualcomm.com).
