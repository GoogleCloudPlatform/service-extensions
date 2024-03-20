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
FROM marketplace.gcr.io/google/debian12
RUN apt-get update && apt-get install -y python3-pip python3-grpc-tools
WORKDIR /home/callouts/python
COPY ./extproc/service ./extproc/service
COPY ./extproc/proto ./extproc/proto
COPY ./extproc/ssl_creds ./extproc/ssl_creds
COPY ./extproc/example/add_custom_response ./extproc/example/add_custom_response
EXPOSE 443
EXPOSE 8080
EXPOSE 80
CMD [ "/usr/bin/python3", "-um", "extproc.example.add_custom_response.service_callout_example" ]
