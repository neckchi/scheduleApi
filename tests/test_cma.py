import app.api.carrier_api.cma
from app.api.carrier_api.cma import get_cma_p2p, process_schedule_data, process_leg_data, \
    DEFAULT_ETD_ETA
import app.internal.setting as config
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import yaml
from types import GeneratorType

# Get the absolute path to the config.py file
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'config.py'))

# Add the parent directory of app to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(config_path)))

# Import the actual config module

# Read the actual configmap.yaml file
configmap_path = os.path.join(os.path.dirname(config_path), 'configmap.yaml')
with open(configmap_path, 'r') as f:
    configmap_content = yaml.safe_load(f)

# Mock the load_yaml function to return the actual content of configmap.yaml
config.load_yaml = lambda: configmap_content

# Mock the redis_mgr module
sys.modules['app.storage.redis_mgr'] = MagicMock()


# Mock HTTPClientWrapper
class MockHTTPClientWrapper:
    async def parse(self, scac, method, url, params, headers):
        # This will be overridden in tests
        pass


@pytest.fixture
def mock_client():
    return MockHTTPClientWrapper()


@pytest.fixture
def mock_process_schedule_data():
    with patch('app.carrierp2p.cma.process_schedule_data') as mock:
        mock.return_value = iter([{'processed': 'data'}])
        yield mock


@pytest.fixture
def sample_leg_data():
    return [{
        "pointFrom": {
            "location": {
                "name": "Shanghai",
                "internalCode": "CNSHA",
                "locationCodifications": [{"codification": "SHA"}],
                "facility": {
                    "name": "Terminal A",
                    "facilityCodifications": [{"codification": "TERM1"}]
                }
            },
            "departureDateLocal": "2024-01-01T12:00:00",
            "cutOff": {
                "shippingInstructionAcceptance": {"local": "2024-01-01T10:00:00"},
                "portCutoff": {"local": "2024-01-01T11:00:00"},
                "vgm": {"local": "2024-01-01T09:00:00"}
            }
        },
        "pointTo": {
            "location": {
                "name": "Singapore",
                "internalCode": "SGSIN",
                "locationCodifications": [{"codification": "SIN"}],
                "facility": {
                    "name": "Terminal B",
                    "facilityCodifications": [{"codification": "TERM2"}]
                }
            },
            "arrivalDateLocal": "2024-01-05T14:00:00"
        },
        "legTransitTime": 96,
        "transportation": {
            "voyage": {
                "service": {"code": "FAL1"},
                "voyageReference": "123ABC"
            },
            "vehicule": {"reference": "IMO123456"},
            "meanOfTransport": {"Vessel"}
        }
    }]


@pytest.fixture
def sample_schedule_data(sample_leg_data):
    return {
        "transitTime": 96,
        "shippingCompany": "0001",
        "routingDetails": sample_leg_data
    }


def deepget(d, *keys, default=None):
    try:
        for key in keys:
            d = d[key]
        return d
    except (KeyError, TypeError, IndexError):
        return default


class TestGetCmaP2p:

    @pytest.mark.asyncio
    async def test_get_cma_p2p_us_to_us(self, mock_process_schedule_data):
        url = "http://example.com/api"
        pw = "password123"
        pol = "USNYC"
        pod = "USLAX"
        search_range = 7
        direct_only = True

        mock_response = [{"transitTime": 10, "some": "data"}]
        with patch('app.api.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await get_cma_p2p(mock_client, url, pw, pol, pod, search_range, direct_only)
            assert isinstance(result, GeneratorType)

            # Check if fetch_initial_schedules was called with correct parameters
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[1]
            assert call_args['extra_condition']

            # Check the content of the generator
            result_list = list(result)
            assert len(result_list) > 0
            assert result_list[0] == {'processed': 'data'}

    @pytest.mark.asyncio
    async def test_get_cma_p2p_no_results(self, mock_process_schedule_data):
        url = "http://example.com/api"
        pw = "password123"
        pol = "USNYC"
        pod = "CNSHA"
        search_range = 7
        direct_only = True

        with patch('app.api.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            result = await get_cma_p2p(mock_client, url, pw, pol, pod, search_range, direct_only)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_cma_p2p_with_scac(self, mock_process_schedule_data):
        url = "http://example.com/api"
        pw = "password123"
        pol = "USNYC"
        pod = "CNSHA"
        search_range = 7
        direct_only = True
        scac = "CMDU"

        mock_response = [{"transitTime": 10, "some": "data"}]

        with patch('app.api.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await get_cma_p2p(mock_client, url, pw, pol, pod, search_range, direct_only, scac=scac)
            assert isinstance(result, GeneratorType)

            # Check if fetch_initial_schedules was called with correct parameters
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[1]
            assert call_args['cma_list'] == ['0001']  # Assuming '0001' corresponds to 'CMDU' in CMA_GROUP

            # Check the content of the generator
            result_list = list(result)
            assert len(result_list) > 0
            assert result_list[0] == {'processed': 'data'}

    @pytest.mark.asyncio
    async def test_get_cma_p2p_basic(self, mock_process_schedule_data):
        url = "http://example.com/api"
        pw = "password123"
        pol = "USNYC"
        pod = "CNSHA"
        search_range = 7
        direct_only = True

        mock_response = [{"transitTime": 10, "some": "data"}]

        with patch('app.api.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await get_cma_p2p(mock_client, url, pw, pol, pod, search_range, direct_only)
            assert isinstance(result, GeneratorType)

            # Check if fetch_initial_schedules was called with correct parameters
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[1]
            assert call_args['client'] == mock_client
            assert call_args['url'] == url
            assert call_args['headers'] == {'keyID': pw}
            assert 'placeOfLoading' in call_args['params']
            assert 'placeOfDischarge' in call_args['params']
            assert call_args['cma_list'] == [None, '0015']

            # Check the content of the generator
            result_list = list(result)
            assert len(result_list) > 0
            assert result_list[0] == {'processed': 'data'}

            # Check if process_schedule_data was called with correct parameters
            mock_process_schedule_data.assert_called_once_with(
                task={"transitTime": 10, "some": "data"},
                direct_only=direct_only,
                service_filter=None,
                vessel_imo_filter=None
            )


class TestProcessLegData:
    def test_basic_processing(self, sample_leg_data):
        """Test basic leg data processing with complete data"""
        result = process_leg_data(sample_leg_data)

        assert len(result) == 1
        leg = result[0]

        # Verify point from details
        assert leg.pointFrom.locationName == "Shanghai"
        assert leg.pointFrom.locationCode == "CNSHA"
        assert leg.pointFrom.terminalName == "Terminal A"
        assert leg.pointFrom.terminalCode == "TERM1"

        # Verify point to details
        assert leg.pointTo.locationName == "Singapore"
        assert leg.pointTo.locationCode == "SGSIN"
        assert leg.pointTo.terminalName == "Terminal B"
        assert leg.pointTo.terminalCode == "TERM2"

        # Verify other leg details
        assert leg.transitTime == 96
        assert leg.services.serviceCode == "FAL1"
        assert leg.voyages.internalVoyage == "123ABC"

        # Verify cutoff times
        assert leg.cutoffs.docCutoffDate == "2024-01-01T10:00:00"
        assert leg.cutoffs.cyCutoffDate == "2024-01-01T11:00:00"
        assert leg.cutoffs.vgmCutoffDate == "2024-01-01T09:00:00"

    def test_missing_optional_fields(self, sample_leg_data):
        """Test leg data processing with missing optional fields"""
        # Remove optional fields
        leg_data = sample_leg_data.copy()
        leg_data[0]["pointFrom"]["location"]["facility"] = None
        leg_data[0]["transportation"]["voyage"]["service"] = None
        leg_data[0]["pointFrom"]["cutOff"] = None

        result = process_leg_data(leg_data)
        assert len(result) == 1
        leg = result[0]

        assert leg.pointFrom.terminalName is None
        assert leg.pointFrom.terminalCode is None
        assert leg.services is None
        assert leg.cutoffs is None


class TestProcessScheduleData:
    def test_direct_route(self, sample_schedule_data):
        """Test schedule data processing for direct route"""
        schedules = list(
            process_schedule_data(sample_schedule_data, direct_only=True, service_filter=None, vessel_imo_filter=None))

        assert len(schedules) == 1
        schedule = schedules[0]

        assert schedule.scac == "CMDU"
        assert schedule.pointFrom == "CNSHA"
        assert schedule.pointTo == "SGSIN"
        assert schedule.transitTime == 96
        assert schedule.transshipment is False

    def test_filters(self, sample_schedule_data):
        """Test schedule data processing with service and vessel filters"""
        # Test with matching filters
        schedules = list(process_schedule_data(
            sample_schedule_data,
            direct_only=None,
            service_filter="FAL1",
            vessel_imo_filter="IMO123456"
        ))
        assert len(schedules) == 1

        # Test with non-matching service filter
        schedules = list(process_schedule_data(
            sample_schedule_data,
            direct_only=None,
            service_filter="WRONG",
            vessel_imo_filter="IMO123456"
        ))
        assert len(schedules) == 0

        # Test with non-matching vessel filter
        schedules = list(process_schedule_data(
            sample_schedule_data,
            direct_only=None,
            service_filter="FAL1",
            vessel_imo_filter="WRONG"
        ))
        assert len(schedules) == 0

    def test_missing_dates(self, sample_schedule_data):
        """Test schedule data processing with missing dates"""
        schedule_data = sample_schedule_data.copy()
        schedule_data["routingDetails"][0]["pointFrom"]["departureDateLocal"] = None
        schedule_data["routingDetails"][0]["pointTo"]["arrivalDateLocal"] = None

        schedules = list(
            process_schedule_data(schedule_data, direct_only=None, service_filter=None, vessel_imo_filter=None))
        assert len(schedules) == 1
        schedule = schedules[0]

        assert schedule.etd == DEFAULT_ETD_ETA
        assert schedule.eta == DEFAULT_ETD_ETA

    def test_transshipment(self, sample_schedule_data, sample_leg_data):
        """Test schedule data processing with transshipment"""
        # Add a second leg to create a transshipment route
        second_leg = sample_leg_data[0].copy()
        second_leg["pointFrom"]["location"]["name"] = "Singapore"
        second_leg["pointFrom"]["location"]["internalCode"] = "SGSIN"
        second_leg["pointTo"]["location"]["name"] = "Hong Kong"
        second_leg["pointTo"]["location"]["internalCode"] = "HKHKG"

        schedule_data = sample_schedule_data.copy()
        schedule_data["routingDetails"].append(second_leg)

        # Test with direct_only=True (should not yield any schedules)
        schedules = list(
            process_schedule_data(schedule_data, direct_only=True, service_filter=None, vessel_imo_filter=None))
        assert len(schedules) == 0

        # Test with direct_only=False
        schedules = list(
            process_schedule_data(schedule_data, direct_only=False, service_filter=None, vessel_imo_filter=None))
        assert len(schedules) == 1
        schedule = schedules[0]
        assert schedule.transshipment is True
        assert len(schedule.legs) == 2
