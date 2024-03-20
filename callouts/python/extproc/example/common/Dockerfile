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

# Build the proto libraries from envoy git using buf.
FROM bufbuild/buf as BUF
RUN apk add git
COPY ./buf.gen.yaml ./buf.gen.yaml
RUN buf -v generate https://github.com/envoyproxy/envoy.git#subdir=api --path envoy/service/ext_proc/v3/external_processor.proto --include-imports

# Build the callout service. 
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y python3-grpcio --no-install-recommends --no-install-suggests

WORKDIR /home/callouts/python

# Copy over the protobuf files from the buf build.
COPY --from=BUF ./protodef .

# Setup the service callout files.
COPY ./extproc/service ./extproc/service
COPY ./extproc/ssl_creds ./extproc/ssl_creds
