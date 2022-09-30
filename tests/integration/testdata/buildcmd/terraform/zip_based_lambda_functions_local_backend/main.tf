provider "aws" {
    region = "us-west-1"
}

resource "aws_iam_role" "iam_for_lambda" {
    name = "dummy_iam_role"

    assume_role_policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": "sts:AssumeRole",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Effect": "Allow",
            "Sid": ""
        }
    ]
}
EOF
}

locals {
    building_path = "./building"
    lambda_src_path = "./src/list_books"
    lambda_code_filename = "list_books.zip"
    layer_src_path = "./my_layer_code"
    layer_code_filename = "my_layer.zip"
}

resource "random_uuid" "s3_bucket" {
    keepers = {
        my_key = "my_key"
    }
}

resource "aws_s3_bucket" "lambda_code_bucket" {
    # bucket = "lambda_code_bucket-${random_uuid.s3_bucket.result}"
    bucket = "lambda_code_bucket"
}

resource "aws_s3_object" "s3_lambda_code" {
    bucket = aws_s3_bucket.lambda_code_bucket.bucket
    key = "s3_lambda_code"
    source = "${local.building_path}/${local.lambda_code_filename}"
}

resource "null_resource" "build_lambda_function" {
    triggers = {
        build_number = "${timestamp()}"
    }

    provisioner "local-exec" {
        command = "./py_build.sh \"${local.lambda_src_path}\" \"${local.building_path}\" \"${local.lambda_code_filename}\""
    }
}

resource "null_resource" "build_layer_version" {
    triggers = {
        build_number = "${timestamp()}"
    }

    provisioner "local-exec" {
        command = "./py_build.sh \"${local.layer_src_path}\" \"${local.building_path}\" \"${local.layer_code_filename}\""
    }
}


## /* Lambda Function with code from a local file ###
resource "aws_lambda_function" "from_localfile" {
    filename = "${local.building_path}/${local.lambda_code_filename}"
    handler = "index.lambda_handler"
    runtime = "python3.8"
    function_name = "my_function_from_localfile"
    role = aws_iam_role.iam_for_lambda.arn
    depends_on = [
        null_resource.build_lambda_function
    ]
}

resource "null_resource" "sam_metadata_aws_lambda_function_from_localfile" {
    triggers = {
        resource_name = "aws_lambda_function.from_localfile"
        resource_type = "ZIP_LAMBDA_FUNCTION"
        original_source_code = local.lambda_src_path
        built_output_path = "${local.building_path}/${local.lambda_code_filename}"
    }
    depends_on = [
        null_resource.build_lambda_function
    ]
}
## */

## /* Lambda Function with code from S3
resource "aws_lambda_function" "from_s3" {
    s3_bucket = aws_s3_bucket.lambda_code_bucket.bucket
    s3_key = aws_s3_object.s3_lambda_code.key
    handler = "index.lambda_handler"
    runtime = "python3.8"
    function_name = "my_function_from_s3"
    role = aws_iam_role.iam_for_lambda.arn
    depends_on = [
        null_resource.build_lambda_function
    ]    
}

resource "null_resource" "sam_metadata_aws_lambda_function_from_s3" {
    triggers = {
        resource_name = "aws_lambda_function.from_s3"
        resource_type = "ZIP_LAMBDA_FUNCTION"
        original_source_code = local.lambda_src_path
        built_output_path = "${local.building_path}/${local.lambda_code_filename}"
    }
    depends_on = [
        null_resource.build_lambda_function
    ]
}
## */

## /* Level1 Lambda Module and Level2 Lambda Module
module "level1_lambda" {
    source = "./lambda_tf_module"
    source_code_path = "${local.building_path}/${local.lambda_code_filename}"
    handler = "index.lambda_handler"
    function_name = "my_level1_lambda"
    l2_source_code_path = "${local.building_path}/${local.lambda_code_filename}"
    l2_handler = "index.lambda_handler"
    l2_function_name = "my_level2_lambda"
    depends_on = [
        null_resource.build_lambda_function
    ]
}

resource "null_resource" "sam_metadata_aws_lambda_function_level1_lambda" {
    triggers = {
        resource_name = "module.level1_lambda.aws_lambda_function.this"
        resource_type = "ZIP_LAMBDA_FUNCTION"
        original_source_code = local.lambda_src_path
        built_output_path = "${local.building_path}/${local.lambda_code_filename}"
    }
    depends_on = [
        null_resource.build_lambda_function
    ] 
}

resource "null_resource" "sam_metadata_aws_lambda_function_level2_lambda" {
    triggers = {
        resource_name = "module.level1_lambda.module.level2_lambda.aws_lambda_function.this"
        resource_type = "ZIP_LAMBDA_FUNCTION"
        original_source_code = local.lambda_src_path
        built_output_path = "${local.building_path}/${local.lambda_code_filename}"
    }
    depends_on = [
        null_resource.build_lambda_function
    ] 
}
## */

## /* Lambda Layer with local source code
resource "aws_lambda_layer_version" "from_local" {
    filename = "${local.building_path}/${local.layer_code_filename}"
    layer_name = "my_layer"

    compatible_runtimes = ["python3.8", "python3.9"]
}

resource "null_resource" "sam_metadata_aws_lambda_layer_version_from_local" {
    triggers = {
        resource_name = "aws_lambda_layer_version.from_local"
        resource_type = "LAMBDA_LAYER"

        original_source_code = local.layer_src_path
        source_code_property = "path"
        built_output_path = "${local.building_path}/${local.layer_code_filename}"
    }
    depends_on = [
        null_resource.build_layer_version
    ]
}
## */