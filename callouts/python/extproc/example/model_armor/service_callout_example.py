# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import enum
import json
import logging
import os
from typing import Tuple

from envoy.service.ext_proc.v3 import external_processor_pb2 as service_pb2
from envoy.type.v3 import http_status_pb2
from extproc.service import callout_server, callout_tools
from google.api_core.client_options import ClientOptions
from google.cloud import modelarmor_v1
from grpc import ServicerContext


class InputType(str, enum.Enum):
    """Enum class for type of text to screen"""

    PROMPT = "prompt"
    MODEL_RESPONSE = "model_response"


def screen_text(text: str, text_type: InputType) -> Tuple[bool, str]:
    """Screen provided text with model armor.

    Args:
        text (str): string data to screen.
        text_type (InputType): type of text to screen (prompt or model response).
    Returns:
        is_valid (bool): boolean value to indicate if text is valid.
        sanitized_text (str): The sanitized text if de-identified value received from model armor or original text.
    """
    # Initialize prompt validation status and final prompt
    is_invalid = False
    sanitized_text = text

    # Location for model armor client and template
    location = os.environ.get("MA_LOCATION")

    if not location:
        logging.warning("`MA_LOCATION` environment variable not found.")
        return is_invalid, sanitized_text

    # Create the model armor client
    client = modelarmor_v1.ModelArmorClient(
        transport="rest",
        client_options=ClientOptions(
            api_endpoint=f"modelarmor.{location}.rep.googleapis.com"
        ),
    )

    # Model Armor template
    model_armor_template = os.environ.get("MA_TEMPLATE")

    # If model armor template is not found, return invalid
    if not model_armor_template:
        logging.warning("`MA_TEMPLATE` environment variable not found.")
        return is_invalid, sanitized_text

    # Get the findings for prompt if text type is user prompt
    if text_type == InputType.PROMPT:
        screen_response = client.sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=model_armor_template,
                user_prompt_data=modelarmor_v1.DataItem(text=text),
            )
        )
    # Get the findings for model response if type is model response
    elif text_type == InputType.MODEL_RESPONSE:
        screen_response = client.sanitize_model_response(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=model_armor_template,
                user_prompt_data=modelarmor_v1.DataItem(text=text),
            )
        )
    else:
        # Return invalid if text type is not prompt or model response
        logging.warning(
            "Invalid text type received. It should be either prompt or model response"
        )
        return is_invalid, sanitized_text

    # Check if Match Found for any filter
    if (
        screen_response.sanitization_result.filter_match_state
        == modelarmor_v1.FilterMatchState.MATCH_FOUND
    ):
        # If Advanced SDP filter is enabled in the template,
        # check if the response contains de-identified content.
        if (
            screen_response.sanitization_result.filter_results.get(
                "sdp"
            ).sdp_filter_result.deidentify_result.match_state
            == modelarmor_v1.FilterMatchState.MATCH_FOUND
        ):
            sanitized_text = (
                screen_response.sanitization_result.filter_results.get(
                    "sdp"
                ).sdp_filter_result.deidentify_result.data.text
                or text
            )
        # Mark prompt invalid for other filter match
        else:
            is_invalid = True

    # Return final finding result and original/sanitized text
    return is_invalid, sanitized_text


class CalloutServerExample(callout_server.CalloutServer):
    """Example callout server with external screening service integration."""

    def on_request_body(self, body: service_pb2.HttpBody, context: ServicerContext):
        """Custom processor on the request body.

        Args:
            body (service_pb2.HttpBody): The HTTP body received in the request.
            context (ServicerContext): The context object for the gRPC service.

        Returns:
            service_pb2.BodyResponse: The response containing the mutations to be applied
            to the request body.
        """
        body_content = f"{body.body.decode('utf-8')}".strip()
        if not body_content:
            return callout_tools.add_body_mutation()

        try:
            body_json = json.loads(body_content)
        except json.JSONDecodeError:
            context.abort(
                http_status_pb2.StatusCode.InvalidArgument, "Invalid JSONBody"
            )

        # TODO (Developer) : Update parsing prompt from request body
        # according to expected request body format
        prompt = body_json.get("prompt", "")
        if not prompt:
            return callout_tools.add_body_mutation()

        is_invalid_prompt, valid_prompt = screen_text(prompt, InputType.PROMPT)
        if is_invalid_prompt:
            # Stop request for invalid prompts
            return callout_tools.header_immediate_response(
                code=http_status_pb2.StatusCode.Forbidden,
                headers=[
                    (
                        "model-armor-message",
                        "Provided prompt does not comply with Responsible AI filter",
                    )
                ],
            )

        # Allow safe prompts.

        # TODO (Developer) : Update path to changing (sanitized) prompt in request body
        # according to expected request body format
        body_json["prompt"] = valid_prompt
        return callout_tools.add_body_mutation(body=json.dumps(body_json))

    def on_response_body(self, body: service_pb2.HttpBody, context: ServicerContext):
        """Custom processor on the response body.

        Args:
            body (service_pb2.HttpBody): The HTTP body received in the response.
            context (ServicerContext): The context object for the gRPC service.

        Returns:
            service_pb2.BodyResponse: The response containing the mutations to be applied
            to the response body.
        """
        body_content = f"{body.body.decode('utf-8')}".strip()
        if not body_content:
            return callout_tools.add_body_mutation()

        try:
            response_body_json = json.loads(body_content)
        except json.JSONDecodeError:
            context.abort(
                http_status_pb2.StatusCode.InvalidArgument, "Invalid JSON response body"
            )

        # TODO (Developer) : Update parsing model response from response body
        # according to expected response format
        model_response = response_body_json["choices"][0]["message"]["content"]

        if not model_response:
            return callout_tools.add_body_mutation()

        is_invalid_model_response, valid_model_response = screen_text(
            model_response, InputType.MODEL_RESPONSE
        )
        if is_invalid_model_response:
            # Deny if Model Armor flags the model's response as unsafe.
            return callout_tools.deny_callout(
                context,
                msg="Model response violates responsible AI filters. Update the prompt or contact application admin if issue persists.",
            )

        # Allow safe model response

        # TODO (Developer) : Update path to changing (sanitized) model response in response body
        # according to expected response format
        response_body_json["choices"][0]["message"]["content"] = valid_model_response
        return callout_tools.add_body_mutation(body=json.dumps(response_body_json))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # Run the gRPC service
    CalloutServerExample().run()
