import logging
import requests
import time
from xml.etree import ElementTree


def create_message(alert):
    """
    Creates a key-value formatted message for Splunk that contains parsed data from FlexT. Defaulting to parsing
    empty values.

    :param alert: Parsed alert data from FlexT
    :return: Returns formatted string.
    """
    data = alert.getAllFields(dictionary=True, parseEmpty=True)
    message = "{0} LQMT: ".format(time.asctime())
    for key, value in data.items():
        message += "{0}={1} ".format(key, value)

    return message


class ApiHandler:
    """
    Class for handling API calls to Splunk's REST Api. This class might end up being redundant depending on a few
    things, but that will be fleshed out further as the tool is built.
    """

    def __init__(self, host=None, port=None, username=None, password=None, splunk_token="", cert_check=True,
                 source=None, sourcetype=None, index=None):
        self._messages_processed = 0
        self._logger = logging.getLogger("LQMT.Splunk.ApiCaller")
        self.host = host
        self.port = port
        self.source = source
        self.sourcetype = sourcetype
        self.index = index
        self.cert_check = cert_check
        self.url = self.host + ":" + str(self.port)
        self.username = username
        self.password = password
        self.requests = requests
        self.authenticated = False
        self.splunk_token = {'Authorization': splunk_token}
        self.auth_service = "/services/auth/login/"
        self.stream_service = "/services/receivers/stream/"

        # Call authentication function when class object is created.
        self.authenticate()

    def __enter__(self):
        self.authenticate()
        return self

    def __exit__(self):
        self._logger.debug("Total messages processed: {0}".format(self._messages_processed))
        self.requests.post(url=self.url, headers={'Connection': 'close'}, verify=self.cert_check)

    def authenticate(self):
        """
        Method for authenticating against Splunk's REST Api. Returns a session token that will be used for future
        connections. If authentication fails, then the lqmt closes out with an error.
        :return: String: splunk_token. Value containing the splunk token provided by Splunk
        """
        # Check to make sure we aren't already authenticated
        if not self.authenticated:
            # Format username and password, then send the request
            data = {'username': self.username, 'password': self.password}
            r = self.requests.post(self.url + self.auth_service, data=data, verify=self.cert_check)

            # If authentication is successful, then pull out the token and set our auth status. If not, weep.
            if r.ok:
                data = ElementTree.fromstring(r.content)
                self.splunk_token['Authorization'] = "Splunk " + data[0].text
                self.authenticated = True
                self._logger.debug(
                    "Successfully authenticated with Splunk instance. Token received: {0}".format(data[0].text)
                )
            else:
                r.raise_for_status()

            return self.splunk_token

    def send_message(self, message, source=None, sourcetype=None, index=None):
        """
        Method for sending messages to Splunk via REST api. If the authentication function hasn't been run yet, then
        it is called.
        :param source: Used to override previously set source value
        :param sourcetype: Used to override previously set sourcetype
        :param index:
        :param message: message to be sent to splunk
        """

        # Override's for source, sourcetype, and index
        if source is not None:
            self.source = source

        if sourcetype is not None:
            self.sourcetype = sourcetype

        if index is not None:
            self.index = index

        # If not authenticated, then authenticate
        if not self.authenticated:
            self.authenticate()

        # Mom says to properly format your headers
        headers = {"x-splunk-input-mode": "streaming"}
        headers = dict(list(self.splunk_token.items()) + list(headers.items()))

        # Build url for api and send the api request
        url = self.url + self.stream_service + "?source={0}&sourcetype={1}&index={2}".format(
            self.source,
            self.sourcetype,
            self.index
        )
        r = self.requests.post(url, data=message, headers=headers, verify=self.cert_check)

        # If parsed successfully, tally and move on. Otherwise raise status
        if r.ok:
            self._messages_processed += 1
        else:
            r.raise_for_status()

        self._logger.debug("Message sent to Splunk. Status code returned: {0}".format(r.status_code))

    def getTotalMessagesProcessed(self):
        return self._messages_processed
