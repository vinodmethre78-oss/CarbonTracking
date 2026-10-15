"""Emergency trip reassignment (spec sections 19-21, 46)."""
import pytest
from models.db import db, Driver, Vehicle, Trip
from routes.auth_utils import hash_password, generate_token


def _create_trip(client, driver_headers, **overrides):
    payload = {"source": "Bengaluru", "destination": "Mysuru", "distance_km": 150,
               "dest_lat": 12.2958, "dest_lng": 76.6394}
    payload.update(overrides)
    return client.post("/api/v1/trips", json=payload, headers=driver_headers)


def _ongoing_trip(client, driver_headers):
    trip_id = _create_trip(client, driver_headers).get_json()["id"]
    client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
    return trip_id


@pytest.fixture()
def other_approved_driver(app, vehicle):
    """A second Approved driver, on a different vehicle, eligible to receive
    a reassigned trip."""
    with app.app_context():
        v2 = Vehicle(vehicle_code="V0002", vehicle_no="KA02CD5678", vehicle_type="Truck",
                     fuel_type="Diesel", mileage=9.0, capacity_kg=2000, health_score=95, status="Active")
        db.session.add(v2)
        db.session.commit()
        d = Driver(driver_code="D0003", name="Backup Driver", username="driver3",
                    password_hash=hash_password("Driver@12345"), email="driver3@example.com",
                    phone="9876511111", status="Approved", assigned_vehicle_id=v2.id)
        db.session.add(d)
        db.session.commit()
        return {"id": d.id, "username": "driver3"}


def _other_driver_headers(app, other_approved_driver):
    with app.app_context():
        token = generate_token(other_approved_driver["id"], "driver")
    return {"Authorization": f"Bearer {token}"}


class TestDriverRequestsReassignment:
    def test_driver_requests_reassignment(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                         json={"reason": "Vehicle Breakdown", "description": "Engine overheating on the highway."},
                         headers=driver_headers)
        assert r.status_code == 201
        body = r.get_json()
        assert body["status"] == "Pending"
        assert body["trip_id"] == trip_id

    def test_invalid_reason_rejected(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                         json={"reason": "I feel like it"}, headers=driver_headers)
        assert r.status_code == 400

    def test_other_reason_requires_description(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                         json={"reason": "Other"}, headers=driver_headers)
        assert r.status_code == 400

    def test_cannot_request_reassignment_for_non_ongoing_trip(self, client, driver_headers):
        trip_id = _create_trip(client, driver_headers).get_json()["id"]  # still Planned
        r = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                         json={"reason": "Medical Emergency"}, headers=driver_headers)
        assert r.status_code == 400

    def test_duplicate_pending_request_rejected(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                    json={"reason": "Medical Emergency"}, headers=driver_headers)
        r = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                         json={"reason": "Medical Emergency"}, headers=driver_headers)
        assert r.status_code == 409


class TestAdminReviewsReassignment:
    def test_admin_receives_request(self, client, driver_headers, admin_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                    json={"reason": "Accident / Safety Issue"}, headers=driver_headers)
        r = client.get("/api/v1/admin/reassignment-requests?status=Pending", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.get_json()) == 1
        assert r.get_json()[0]["trip_id"] == trip_id

    def test_admin_rejects_request(self, client, driver_headers, admin_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Personal Emergency"}, headers=driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/reject",
                         json={"note": "Please continue, help is 2 minutes away."}, headers=admin_headers)
        assert r.status_code == 200
        assert r.get_json()["status"] == "Rejected"
        # Trip is untouched and still belongs to the original driver.
        trip = client.get(f"/api/v1/trips/{trip_id}", headers=driver_headers).get_json()
        assert trip["status"] == "Ongoing"

    def test_admin_approves_and_replacement_driver_continues_same_trip(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        trip_id = _ongoing_trip(client, driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Vehicle Problem"}, headers=driver_headers).get_json()["id"]

        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/approve",
                         json={"replacement_driver_id": other_approved_driver["id"]}, headers=admin_headers)
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "Approved"
        assert body["replacement_driver_id"] == other_approved_driver["id"]

        # Same trip id, still Ongoing — not a new/duplicate trip.
        with app.app_context():
            trip = db.session.get(Trip, trip_id)
            assert trip.status == "Ongoing"
            assert trip.driver_id == other_approved_driver["id"]

        # The new driver can see it as their active trip and eventually finish it.
        new_headers = _other_driver_headers(app, other_approved_driver)
        active = client.get("/api/v1/driver/active-trip", headers=new_headers).get_json()
        assert active["trip"]["id"] == trip_id

        client.post(f"/api/v1/driver/trips/{trip_id}/location",
                    json={"lat": 12.2958, "lng": 76.6394, "accuracy": 10}, headers=new_headers)
        end = client.post(f"/api/v1/trips/{trip_id}/end",
                           json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=new_headers)
        assert end.status_code == 200
        assert end.get_json()["status"] == "Completed"

    def test_approve_rejects_ineligible_replacement_driver(self, client, driver_headers, admin_headers, pending_driver):
        trip_id = _ongoing_trip(client, driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Unable to Continue"}, headers=driver_headers).get_json()["id"]
        # pending_driver is not Approved — must be rejected as a replacement.
        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/approve",
                         json={"replacement_driver_id": pending_driver["id"]}, headers=admin_headers)
        assert r.status_code == 400
        assert r.get_json()["code"] == "DRIVER_NOT_ELIGIBLE"

    def test_driver_cannot_approve_own_request(self, client, driver_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Medical Emergency"}, headers=driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/approve",
                         json={"replacement_driver_id": 1}, headers=driver_headers)
        assert r.status_code == 403

    def test_already_resolved_request_cannot_be_resolved_again(self, client, driver_headers, admin_headers):
        trip_id = _ongoing_trip(client, driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Medical Emergency"}, headers=driver_headers).get_json()["id"]
        client.post(f"/api/v1/admin/reassignment-requests/{req_id}/reject", json={}, headers=admin_headers)
        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/reject", json={}, headers=admin_headers)
        assert r.status_code == 409


class TestReassignedDriverLiveMap:
    """After an admin approves a reassignment, the replacement driver must be
    able to rebuild the live map for the SAME trip from GET /driver/active-trip,
    the original driver must be locked out, and the GPS safety checks must be
    evaluated per-driver rather than against the previous driver's pings."""

    ROUTE = [(12.9716, 77.5946), (12.6, 77.2), (12.2958, 76.6394)]

    def _reassigned(self, app, client, driver_headers, admin_headers, other_approved_driver):
        import polyline as polyline_lib
        encoded = polyline_lib.encode(self.ROUTE)
        trip_id = _create_trip(client, driver_headers, route_polyline=encoded).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        # Driver A reports a position near the START of the route.
        a = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                        json={"lat": 12.9716, "lng": 77.5946, "accuracy": 10}, headers=driver_headers)
        assert a.status_code == 201
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Vehicle Breakdown"}, headers=driver_headers).get_json()["id"]
        r = client.post(f"/api/v1/admin/reassignment-requests/{req_id}/approve",
                         json={"replacement_driver_id": other_approved_driver["id"]}, headers=admin_headers)
        assert r.status_code == 200
        return trip_id, encoded, _other_driver_headers(app, other_approved_driver)

    def test_active_trip_returns_route_polyline_for_replacement_driver(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        trip_id, encoded, new_headers = self._reassigned(app, client, driver_headers, admin_headers, other_approved_driver)
        trip = client.get("/api/v1/driver/active-trip", headers=new_headers).get_json()["trip"]
        assert trip["id"] == trip_id
        assert trip["status"] == "Ongoing"
        assert trip["route_polyline"] == encoded
        for k in ("source", "destination", "dest_lat", "dest_lng", "origin_lat", "estimated_duration_min", "distance_km"):
            assert k in trip

        with app.app_context():
            assert Trip.query.count() == 1  # no duplicate trip was created

    def test_route_polyline_not_added_to_list_endpoints(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        _, _, new_headers = self._reassigned(app, client, driver_headers, admin_headers, other_approved_driver)
        listed = client.get("/api/v1/driver/trips", headers=new_headers).get_json()
        assert listed and "route_polyline" not in listed[0]

    def test_original_driver_loses_access(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        trip_id, _, _ = self._reassigned(app, client, driver_headers, admin_headers, other_approved_driver)
        ping = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                           json={"lat": 12.9, "lng": 77.5, "accuracy": 10}, headers=driver_headers)
        assert ping.status_code == 403
        flat = client.post("/api/v1/driver/location",
                           json={"trip_id": trip_id, "lat": 12.9, "lng": 77.5}, headers=driver_headers)
        assert flat.status_code == 403
        assert client.patch(f"/api/v1/driver/trips/{trip_id}/route",
                            json={"route_polyline": "abc"}, headers=driver_headers).status_code == 403
        end = client.post(f"/api/v1/trips/{trip_id}/end",
                          json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=driver_headers)
        assert end.status_code == 403
        assert client.get("/api/v1/driver/active-trip", headers=driver_headers).get_json()["trip"] is None

    def test_replacement_first_ping_not_rejected_as_gps_jump(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        trip_id, _, new_headers = self._reassigned(app, client, driver_headers, admin_headers, other_approved_driver)
        # ~100 km from Driver A's last fix, seconds later: would be an
        # "impossible speed" if measured against A's ping.
        r = client.post(f"/api/v1/driver/trips/{trip_id}/location",
                        json={"lat": 12.2958, "lng": 76.6394, "accuracy": 10}, headers=new_headers)
        assert r.status_code == 201, r.get_json()

    def test_previous_drivers_ping_cannot_unlock_end_trip(
        self, app, client, driver_headers, admin_headers, other_approved_driver
    ):
        # Driver A pinged AT the destination, then was replaced. The new driver
        # has not reported any position yet, so End Trip must stay locked.
        import polyline as polyline_lib
        trip_id = _create_trip(client, driver_headers,
                               route_polyline=polyline_lib.encode(self.ROUTE)).get_json()["id"]
        client.post(f"/api/v1/trips/{trip_id}/start", headers=driver_headers)
        client.post(f"/api/v1/driver/trips/{trip_id}/location",
                    json={"lat": 12.2958, "lng": 76.6394, "accuracy": 10}, headers=driver_headers)
        req_id = client.post(f"/api/v1/driver/trips/{trip_id}/reassignment-request",
                              json={"reason": "Vehicle Breakdown"}, headers=driver_headers).get_json()["id"]
        client.post(f"/api/v1/admin/reassignment-requests/{req_id}/approve",
                    json={"replacement_driver_id": other_approved_driver["id"]}, headers=admin_headers)
        new_headers = _other_driver_headers(app, other_approved_driver)

        active = client.get("/api/v1/driver/active-trip", headers=new_headers).get_json()
        assert active["destination_status"]["end_trip_allowed"] is False
        end = client.post(f"/api/v1/trips/{trip_id}/end",
                          json={"actual_fuel_l": 10, "actual_fuel_price": 95}, headers=new_headers)
        assert end.status_code == 400
        assert end.get_json()["code"] == "LOCATION_UNAVAILABLE"
