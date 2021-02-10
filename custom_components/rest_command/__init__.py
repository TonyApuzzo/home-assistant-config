"""Support for exposing regular REST commands as services."""
import logging

import httpx

from homeassistant.helpers.httpx_client import get_async_client

import voluptuous as vol

from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    HTTP_BAD_REQUEST,
    HTTP_BASIC_AUTHENTICATION,
    HTTP_DIGEST_AUTHENTICATION
)
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client

import homeassistant.helpers.config_validation as cv

DOMAIN = "rest_command"

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_METHOD = "get"
DEFAULT_VERIFY_SSL = True

SUPPORT_REST_METHODS = ["get", "patch", "post", "put", "delete"]

CONF_CONTENT_TYPE = "content_type"

COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): cv.template,
        vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.All(
            vol.Lower, vol.In(SUPPORT_REST_METHODS)
        ),
        vol.Optional(CONF_AUTHENTICATION): vol.In(
            [HTTP_BASIC_AUTHENTICATION, HTTP_DIGEST_AUTHENTICATION]
        ),
        vol.Optional(CONF_HEADERS): vol.Schema({cv.string: cv.template}),
        vol.Inclusive(CONF_USERNAME, "authentication"): cv.string,
        vol.Inclusive(CONF_PASSWORD, "authentication"): cv.string,
        vol.Optional(CONF_PAYLOAD): cv.template,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(int),
        vol.Optional(CONF_CONTENT_TYPE): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.schema_with_slug_keys(COMMAND_SCHEMA)}, extra=vol.ALLOW_EXTRA
)


async def async_setup(hass, config):
    """Set up the REST command component."""

    @callback
    def async_register_rest_command(name, command_config):
        """Create service for rest command."""
        async_client = get_async_client(hass, command_config.get(CONF_VERIFY_SSL))
        timeout = command_config[CONF_TIMEOUT]
        method = command_config[CONF_METHOD]

        template_url = command_config[CONF_URL]
        template_url.hass = hass

        auth = None
        if CONF_USERNAME in command_config:
            username = command_config[CONF_USERNAME]
            password = command_config.get(CONF_PASSWORD, "")
            if (CONF_AUTHENTICATION in command_config
                    and command_config[CONF_AUTHENTICATION] == HTTP_DIGEST_AUTHENTICATION):
                auth = httpx.DigestAuth(username, password)
            else:
                auth = (username, password)

        template_payload = None
        if CONF_PAYLOAD in command_config:
            template_payload = command_config[CONF_PAYLOAD]
            template_payload.hass = hass

        template_headers = None
        if CONF_HEADERS in command_config:
            template_headers = command_config[CONF_HEADERS]
            for template_header in template_headers.values():
                template_header.hass = hass

        content_type = None
        if CONF_CONTENT_TYPE in command_config:
            content_type = command_config[CONF_CONTENT_TYPE]

        async def async_service_handler(service):
            """Execute an HTTP request."""
            payload = None
            if template_payload:
                payload = bytes(
                    template_payload.async_render(
                        variables=service.data, parse_result=False
                    ),
                    "utf-8",
                )

            request_url = template_url.async_render(
                variables=service.data, parse_result=False
            )

            headers = None
            if template_headers:
                headers = {}
                for header_name, template_header in template_headers.items():
                    headers[header_name] = template_header.async_render(
                        variables=service.data, parse_result=False
                    )

            if content_type:
                if headers is None:
                    headers = {}
                headers["Content-Type"] = content_type

            try:
                response = await async_client.request(
                    method,
                    request_url,
                    data=payload,
                    auth=auth,
                    headers=headers,
                    timeout=timeout,
                )
                _LOGGER.debug(
                    "Success. Url: %s. Status code: %d. Payload: %s",
                    request_url,
                    response.status_code,
                    payload,
                )
            except httpx.RequestError as ex:
                _LOGGER.error("Error fetching data: %s failed with %s", request_url, ex)

        # register services
        hass.services.async_register(DOMAIN, name, async_service_handler)

    for command, command_config in config[DOMAIN].items():
        async_register_rest_command(command, command_config)

    return True
