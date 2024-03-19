# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
FROM bufbuild/buf as BUF
FROM marketplace.gcr.io/google/debian12
RUN apt-get update && apt-get install -y git python3-pip python3-grpc-tools

WORKDIR /home/callouts/python

# Build proto from envoy git using buf and install it as a python package.
COPY --from=BUF /usr/local/bin /usr/local/bin
COPY ./buf.gen.yaml ./buf.gen.yaml
COPY ./protodef/setup.py ./protodef/setup.py
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports
RUN pip install ./protodef --break-system-packages --root-user-action=ignore

COPY ./extproc/service ./extproc/service
COPY ./extproc/ssl_creds ./extproc/ssl_creds
COPY ./extproc/example/normalize_header ./extproc/example/normalize_header
EXPOSE 443
EXPOSE 8080
EXPOSE 80
CMD [ "/usr/bin/python3", "-um", "extproc.example.normalize_header.service_callout_example" ]
