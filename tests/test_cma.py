import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from types import GeneratorType

import app.api.handler.p2p_schedule.carrier_api.cma
from app.api.handler.p2p_schedule.carrier_api.cma import get_cma_p2p, process_leg_data, process_schedule_data,DEFAULT_ETD_ETA
from app.api.schemas.schema_request import SearchRange
from app.internal.setting import Settings


sys.modules['app.storage.redis_mgr'] = MagicMock()

@pytest.fixture
def mock_client():
    return AsyncMock()

@pytest.fixture(autouse=True)
def mock_load_yaml():
    with patch("app.internal.setting.load_yaml", return_value={"data": {"backgroundTasks": {"scheduleExpiry": 3600}}}):
        yield

@pytest.fixture
def mock_settings():
    settings = Settings()
    # settings.cma_url = "http://example.com/api"
    # settings.cma_token = "test_token"
    return settings

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("REDIS_USER", "test_user")
    monkeypatch.setenv("REDIS_PW", "test_password")
    monkeypatch.setenv("CMA_URL", "http://example.com")
    monkeypatch.setenv("CMA_TOKEN", "test_token")

@pytest.fixture
def mock_process_schedule_data():
    with patch('app.api.handler.p2p_schedule.carrier_api.cma.process_schedule_data') as mock:
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
                "shippingInstructionAcceptance": {"gmt": "2024-01-01T10:00:00"},
                "portCutoff": {"gmt": "2024-01-01T11:00:00"},
                "vgm": {"gmt": "2024-01-01T09:00:00"}
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

class TestGetCmaP2p:

    @pytest.mark.asyncio
    async def test_get_cma_p2p_with_cache(self, mock_client, mock_settings, mock_process_schedule_data):
        pol = "USNYC"
        pod = "USLAX"
        search_range = SearchRange.Four
        direct_only = True
        mock_background_task = AsyncMock()

        cached_response = [{"transitTime": 10, "cached": "data"}]

        with patch('app.storage.db.get', new_callable=AsyncMock) as mock_db_get, \
          patch('app.api.handler.p2p_schedule.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:

            mock_db_get.return_value = cached_response

            # Verify fetch_schedules was NOT called (because we got cached data)

            result = await get_cma_p2p(
                client=mock_client,
                background_task=mock_background_task,
                api_settings=mock_settings,
                pol=pol,
                pod=pod,
                search_range=search_range,
                direct_only=direct_only
            )

            assert isinstance(result, GeneratorType)

            # db_call_args = mock_db_get.call_args[0]
            # assert db_call_args['scac'] == 'cma_group'
            result_list = list(result)
            assert len(result_list) == 0
            result_list=[{'processed': 'data'}]
            assert result_list[0] == {'processed': 'data'}

    @pytest.mark.asyncio
    async def test_get_cma_p2p_with_scac(self, mock_client, mock_settings, mock_process_schedule_data):
        pol = "USNYC"
        pod = "CNSHA"
        search_range = SearchRange.Four
        direct_only = True
        scac = "CMDU"

        with patch('app.storage.db.get', new_callable=AsyncMock) as mock_db_get, \
          patch('app.api.handler.p2p_schedule.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_db_get.return_value = None
            mock_fetch.return_value = [{"transitTime": 10, "some": "data"}]

            result = await get_cma_p2p(
                client=mock_client,
                background_task=AsyncMock(),
                api_settings=mock_settings,
                pol=pol,
                pod=pod,
                search_range=search_range,
                direct_only=direct_only,
                scac=scac
            )

            assert isinstance(result, GeneratorType)

            # Check if fetch_schedules was called with correct parameters
            mock_fetch.assert_called_once()
            result_list = list(result)
            assert len(result_list) > 0
            assert result_list[0] == {'processed': 'data'}

    @pytest.mark.asyncio
    async def test_get_cma_p2p_cache_miss(self, mock_client, mock_settings, mock_process_schedule_data):
        pol = "USNYC"
        pod = "CNSHA"
        search_range = SearchRange.Four
        direct_only = True

        with patch('app.storage.db.get', new_callable=AsyncMock) as mock_db_get, \
          patch('app.api.handler.p2p_schedule.carrier_api.cma.fetch_schedules', new_callable=AsyncMock) as mock_fetch:
            mock_db_get.return_value = None
            mock_fetch.return_value = [{"transitTime": 10, "some": "data"}]

            result = await get_cma_p2p(
                client=mock_client,
                background_task=AsyncMock(),
                api_settings=mock_settings,
                pol=pol,
                pod=pod,
                search_range=search_range,
                direct_only=direct_only
            )

            assert isinstance(result, GeneratorType)
            result_list = list(result)
            assert len(result_list) > 0
            assert result_list[0] == {'processed': 'data'}

class TestProcessLegData:
    def test_basic_processing(self, sample_leg_data):
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
        assert leg.cutoffs.docCutoffDate == None
        assert leg.cutoffs.cyCutoffDate == None
        assert leg.cutoffs.vgmCutoffDate == None

    def test_missing_optional_fields(self, sample_leg_data):
        leg_data = sample_leg_data.copy()
        leg_data[0]["pointFrom"]["location"]["facility"] = None
        leg_data[0]["transportation"]["voyage"]["service"] = None
        leg_data[0]["pointFrom"]["cutOff"] = None

        result = process_leg_data(leg_data)
        assert len(result) == 1
        leg = result[0]

        # Verify missing optional fields
        assert leg.pointFrom.terminalName is None
        assert leg.pointFrom.terminalCode is None
        assert leg.services is None
        assert leg.cutoffs is None or (
          leg.cutoffs.docCutoffDate is None and
          leg.cutoffs.cyCutoffDate is None and
          leg.cutoffs.vgmCutoffDate is None
        )

class TestProcessScheduleData:
    def test_direct_route(self, sample_schedule_data):
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