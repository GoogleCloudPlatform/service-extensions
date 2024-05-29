# Copyright 2024 Google LLC.
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
FROM service-callout-common-python

# Copy over example specific files.
COPY extproc/example/cloud_log/*.py ./

# Set up communication ports.
EXPOSE 443
EXPOSE 80
EXPOSE 8080

# Copy over example specific requirements.
COPY extproc/example/cloud_log/*.txt ./
RUN pip install -r requirements-example.txt --break-system-packages --root-user-action=ignore

# Start the service.
ENTRYPOINT /usr/bin/python3 -um service_callout_example "$@"