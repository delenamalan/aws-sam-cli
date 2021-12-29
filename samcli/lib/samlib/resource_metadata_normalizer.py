"""
Class that Normalizes a Template based on Resource Metadata
"""

import logging
from pathlib import Path
import json

from samcli.lib.iac.cdk.utils import is_cdk_project

RESOURCES_KEY = "Resources"
PROPERTIES_KEY = "Properties"
METADATA_KEY = "Metadata"

RESOURCE_CDK_PATH_METADATA_KEY = "aws:cdk:path"
ASSET_PATH_METADATA_KEY = "aws:asset:path"
ASSET_PROPERTY_METADATA_KEY = "aws:asset:property"

IMAGE_ASSET_PROPERTY = "Code.ImageUri"
ASSET_DOCKERFILE_PATH_KEY = "aws:asset:dockerfile-path"
ASSET_DOCKERFILE_BUILD_ARGS_KEY = "aws:asset:docker-build-args"

SAM_RESOURCE_ID_KEY = "SamResourceId"
SAM_IS_NORMALIZED = "SamNormalized"
SAM_METADATA_DOCKERFILE_KEY = "Dockerfile"
SAM_METADATA_DOCKER_CONTEXT_KEY = "DockerContext"
SAM_METADATA_DOCKER_BUILD_ARGS_KEY = "DockerBuildArgs"

ASSET_BUNDLED_METADATA_KEY = "aws:asset:is-bundled"
SAM_METADATA_SKIP_BUILD_KEY = "SkipBuild"

LOG = logging.getLogger(__name__)


class ResourceMetadataNormalizer:
    @staticmethod
    def normalize(template_dict, normalize_parameters=False):
        """
        Normalize all Resources in the template with the Metadata Key on the resource.

        This method will mutate the template

        Parameters
        ----------
        template_dict dict
            Dictionary representing the template

        """
        resources = template_dict.get(RESOURCES_KEY, {})

        for logical_id, resource in resources.items():
            resource_metadata = resource.get(METADATA_KEY, {})
            is_normalized = resource_metadata.get(SAM_IS_NORMALIZED, False)
            if not is_normalized:
                asset_property = resource_metadata.get(ASSET_PROPERTY_METADATA_KEY)
                if asset_property == IMAGE_ASSET_PROPERTY:
                    asset_metadata = ResourceMetadataNormalizer._extract_image_asset_metadata(resource_metadata)
                    ResourceMetadataNormalizer._update_resource_metadata(resource_metadata, asset_metadata)
                    # For image-type functions, the asset path is expected to be the name of the Docker image.
                    # When building, we set the name of the image to be the logical id of the function.
                    asset_path = logical_id.lower()
                else:
                    asset_path = resource_metadata.get(ASSET_PATH_METADATA_KEY)

                ResourceMetadataNormalizer._replace_property(asset_property, asset_path, resource, logical_id)
                if asset_path and asset_property:
                    resource_metadata[SAM_IS_NORMALIZED] = True

            # Set SkipBuild metadata iff is-bundled metadata exists, and value is True
            skip_build = resource_metadata.get(ASSET_BUNDLED_METADATA_KEY, False)
            if skip_build:
                ResourceMetadataNormalizer._update_resource_metadata(
                    resource_metadata,
                    {
                        SAM_METADATA_SKIP_BUILD_KEY: True,
                    },
                )

        if normalize_parameters and is_cdk_project(template_dict):
            resources_as_string = json.dumps(resources)
            parameters = template_dict.get("Parameters", {})

            for parameter_name, parameter_value in parameters.items():
                if (
                    parameter_name.startswith("AssetParameters")
                    and "Default" not in parameter_value
                    and parameter_value.get("Type", "") == "String"
                    and f'"Ref": "{parameter_name}"' not in resources_as_string
                ):
                    parameter_value["Default"] = " "

    @staticmethod
    def _replace_property(property_key, property_value, resource, logical_id):
        """
        Replace a property with an asset on a given resource

        This method will mutate the template

        Parameters
        ----------
        property str
            The property to replace on the resource
        property_value str
            The new value of the property
        resource dict
            Dictionary representing the Resource to change
        logical_id str
            LogicalId of the Resource

        """
        if property_key and property_value:
            nested_keys = property_key.split(".")
            target_dict = resource.get(PROPERTIES_KEY, {})
            while len(nested_keys) > 1:
                key = nested_keys.pop(0)
                target_dict[key] = {}
                target_dict = target_dict[key]
            target_dict[nested_keys[0]] = property_value
        elif property_key or property_value:
            LOG.info(
                "WARNING: Ignoring Metadata for Resource %s. Metadata contains only aws:asset:path or "
                "aws:assert:property but not both",
                logical_id,
            )

    @staticmethod
    def _extract_image_asset_metadata(metadata):
        """
        Extract/create relevant metadata properties for image assets

        Parameters
        ----------
        metadata dict
            Metadata to use for extracting image assets properties

        Returns
        -------
        dict
            metadata properties for image-type lambda function

        """
        asset_path = Path(metadata.get(ASSET_PATH_METADATA_KEY, ""))
        dockerfile_path = Path(metadata.get(ASSET_DOCKERFILE_PATH_KEY), "")
        dockerfile, path_from_asset = dockerfile_path.stem, dockerfile_path.parent
        dockerfile_context = str(Path(asset_path.joinpath(path_from_asset)))
        return {
            SAM_METADATA_DOCKERFILE_KEY: dockerfile,
            SAM_METADATA_DOCKER_CONTEXT_KEY: dockerfile_context,
            SAM_METADATA_DOCKER_BUILD_ARGS_KEY: metadata.get(ASSET_DOCKERFILE_BUILD_ARGS_KEY, {}),
        }

    @staticmethod
    def _update_resource_metadata(metadata, updated_values):
        """
        Update the metadata values for image-type lambda functions

        This method will mutate the template

        Parameters
        ----------
        metadata dict
            Metadata dict to be updated
        updated_values dict
            Dict of key-value pairs to append to the existing metadata

        """
        for key, val in updated_values.items():
            metadata[key] = val

    @staticmethod
    def get_resource_id(resource_properties, logical_id):
        """
        Get unique id for a resource.
        for any resource, the resource id can be the customer defined id if exist, if not exist it can be the
        cdk-defined resource id, or the logical id if the resource id is not found.

        Parameters
        ----------
        resource_properties dict
            Properties of this resource
        logical_id str
            LogicalID of the resource

        Returns
        -------
        str
            The unique function id
        """
        resource_metadata = resource_properties.get("Metadata", {})
        customer_defined_id = resource_metadata.get(SAM_RESOURCE_ID_KEY)

        if isinstance(customer_defined_id, str) and customer_defined_id:
            return customer_defined_id

        resource_cdk_path = resource_metadata.get(RESOURCE_CDK_PATH_METADATA_KEY)

        if not isinstance(resource_cdk_path, str) or not resource_cdk_path:
            return logical_id

        # aws:cdk:path metadata format of functions: {stack_id}/{function_id}/Resource
        # Design doc of CDK path: https://github.com/aws/aws-cdk/blob/master/design/construct-tree.md
        cdk_path_partitions = resource_cdk_path.split("/")

        if len(cdk_path_partitions) < 2:
            LOG.warning(
                "Cannot detect function id from aws:cdk:path metadata '%s', using default logical id", resource_cdk_path
            )
            return logical_id

        cdk_resource_id = cdk_path_partitions[-2]

        # Check if the Resource is nested Stack
        if resource_properties.get("Type", "") == "AWS::CloudFormation::Stack" and cdk_resource_id.endswith(
            ".NestedStack"
        ):
            cdk_resource_id = cdk_resource_id[: -len(".NestedStack")]

        return cdk_resource_id
