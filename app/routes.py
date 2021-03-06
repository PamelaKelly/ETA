import pickle

from flask import render_template, jsonify, request, url_for
from flask_cors import cross_origin

from datetime import datetime
from datetime import timedelta

from main import app, log
from db_tools import connect_to_database
from os.path import dirname
from plan_route import find_routes, k_nearest_stop_coords, stop_id

with open('data/sk_linear_model2', 'rb') as f:
    loaded_model = pickle.load(f)

with open('data/2012_tree.pkl', 'rb') as f:
    coords_tree_2012 = pickle.load(f)

from data_loader import loaded_model, loaded_model_weather, loaded_model_without_weather

with open('data/2012_coords_to_id.pkl', 'rb') as f:
    coords_to_id_2012 = pickle.load(f)

# returns, using get_stops_info(), the information on the 5 closest stops to a given lat/lon position.


@app.route("/map_pick/<lat>/<lon>")
def map_pick_stops(lat, lon):
    lat, lon = float(lat), float(lon)
    x = k_nearest_stop_coords(lat, lon, 5, coords_tree_2012)
    stops = []
    for i in x:
        s = stop_id(tuple(i), coords_to_id_2012)
        stops.append(int(s))
    return get_stops_info(tuple(stops))

# returns information for given stop_ids in a tuple

@app.route("/about")
@cross_origin()
def about():
    return(render_template("about.html"))

def get_stops_info(stop_id_list):
    engine = connect_to_database()
    conn = engine.connect()
    stops = []

    rows = conn.execute("SELECT stop_address, stop_id, latitude, longitude FROM eta.bus_stops WHERE \
                        year = 2012 AND stop_id IN {};".format(stop_id_list))
    for row in rows:
        stops.append(dict(row))

    conn.close()
    engine.dispose()

    return jsonify(stops=stops)

# returns index.html


@app.route("/")
def index():
    # https://stackoverflow.com/questions/35246135/flask-request-script-roottojsonsafe-returns-nothing
    if not request.script_root:
        request.script_root = url_for('index', _external=True)

    return render_template("index.html")

# returns rti.html


@app.route("/rti")
def rti():
    return render_template("rti.html")

# returns plan_journey.html


@app.route('/plan_journey')
def plan_journey():
    if not request.script_root:
        request.script_root = url_for('index', _external=True)

    return render_template('plan_journey.html')

# returns routes for the route planner functionality


@app.route('/get_routes', methods=["POST"])
def get_routes():
    log.debug(request.json)

    origin = (request.json['origin']['lat'],
              request.json['origin']['lng'])

    destination = (request.json['destination']['lat'],
                   request.json['destination']['lng'])

    return jsonify(find_routes(origin, destination, max_walk=3000))

# returns information on all stops from database for a given year


@app.route("/stops/<int:year>")
@cross_origin()
def get_stops(year):
    engine = connect_to_database()
    conn = engine.connect()
    stops = []
    if year == 2012:
        rows = conn.execute("SELECT stop_address, stop_id FROM bus_stops WHERE year = 2012 AND stop_id IN \
                            (SELECT stop_id FROM eta.routes) ORDER BY stop_address;")
    else:
        rows = conn.execute(
            "SELECT stop_address, stop_id FROM bus_stops WHERE year = 2017;")

    for row in rows:
        stops.append(dict(row))
    conn.close()
    engine.dispose()
    return jsonify(stops=stops)

# for a given origin stop, returns all destination stops reachable on any route, respecting order on route.


@app.route("/destination_stops/<int:stop_id>")
@cross_origin()
def get_destination_stops(stop_id):
    engine = connect_to_database()
    conn = engine.connect()
    stops = []
    routes = []
    returned_stops = []
    rows = conn.execute("SELECT journey_pattern, position_on_route FROM eta.routes \
                        WHERE stop_id = {};".format(stop_id))
    for row in rows:
        routes.append(dict(row))

    for r in routes:
        jpid = r['journey_pattern']
        distance = r['position_on_route']
        route_stops = conn.execute("SELECT stop_id FROM eta.routes WHERE journey_pattern = {} \
                                   and position_on_route > {};".format("'" + jpid + "'", distance))
        for route_stop in route_stops:
            print(route_stop[0])
            stops.append(route_stop[0])

    stops = tuple(set(stops))
    try:
        stop_rows = conn.execute("SELECT stop_address, stop_id FROM eta.bus_stops \
                                 WHERE year = 2012 AND stop_id in {} ORDER BY stop_address;".format(stops))
        for s in stop_rows:
            returned_stops.append(dict(s))
    except:
        return jsonify(stops=[{'stop_address': 'No Results Found', 'stop_id': 'NA'}])

    # rows = conn.execute("select * from eta.bus_stops where stop_id in (select \
    # 					distinct stop_id from eta.routes where journey_pattern \
    # 					in (select journey_pattern from eta.routes where stop_id \
    # 					= {}) and stop_id != {} and year = 2012) order by stop_address;".format(stop_id, stop_id))
    # for row in rows:
    # 	stops.append(dict(row))
    conn.close()
    engine.dispose()
    return jsonify(stops=returned_stops)

# for given origin and destination stops, returns all routes linking the two, respecting stop order


@app.route("/possible_routes/<int:origin_id>/<int:destination_id>")
@cross_origin()
def get_possible_routes(origin_id, destination_id):
    engine = connect_to_database()
    conn = engine.connect()
    routes = []
    returned_routes = []
    rows = conn.execute("SELECT journey_pattern, line_id FROM eta.routes Where stop_id \
                        = {} and journey_pattern in ( SELECT journey_pattern \
                        FROM eta.routes Where stop_id = {});".format(origin_id, destination_id))
    for row in rows:
        routes.append(dict(row))
    for r in routes:
        # print("r", r)
        jpid = r['journey_pattern']
        o_distance = {}
        d_distance = {}
        o_rows = conn.execute("SELECT position_on_route FROM eta.routes WHERE stop_id = {} AND \
                                journey_pattern = {}".format(origin_id, "'" + jpid + "'", ))

        d_rows = conn.execute("SELECT position_on_route FROM eta.routes WHERE stop_id = {} AND \
                                journey_pattern = {}".format(destination_id, "'" + jpid + "'", ))
        for row in o_rows:
            o_distance.update(dict(row))
        for row in d_rows:
            d_distance.update(dict(row))

        # print("o_distance:", o_distance[0])
        # print("d_distance", d_distance[0])
        if o_distance['position_on_route'] < d_distance['position_on_route']:
            # print("Adding r", r)
            returned_routes.append(dict(r))
    conn.close()
    engine.dispose()
    # print("Returned Routes:", returned_routes)
    return jsonify(routes=returned_routes)

# using pickled models, returns a time prediction for given parameters


@app.route("/predict_time/<int:origin_id>/<int:destination_id>/<int:weekday>/<int:hour>/<jpid>/<rain>")
@cross_origin()
def predict_time(origin_id, destination_id, weekday, hour, jpid, rain):
    rain = float(rain)
    engine = connect_to_database()
    conn = engine.connect()
    o_distance = {}
    d_distance = {}

    origin_distance_list = conn.execute("SELECT position_on_route FROM routes WHERE stop_id = {} AND \
                                        journey_pattern = {};".format(origin_id, "'" + jpid + "'"))

    destination_distance_list = conn.execute("SELECT position_on_route FROM routes WHERE stop_id = {} AND \
                                        journey_pattern = {};".format(destination_id, "'" + jpid + "'"))

    for o in origin_distance_list:
        o_distance.update(dict(o))

    for d in destination_distance_list:
        d_distance.update(dict(d))

    # print("o_distance:", o_distance)
    # print("d_distance:", d_distance)

    origin_distance = o_distance['position_on_route']
    destination_distance = d_distance['position_on_route']


    def get_time(distance, weekday, hour, rain):
        # params = [{
        #   'Distance_Terminal': distance,
        # 	'midweek': weekday,
        # 	'HourOfDay': hour,
        # }]
        #
        # df = pd.DataFrame(params)
        if rain > -1:
            estimated_time = loaded_model_weather.predict(
                [distance, hour, weekday, rain])
        else:
            estimated_time = loaded_model_without_weather.predict(
                [distance, hour, weekday])

        return estimated_time[0]

    origin_time = get_time(origin_distance, weekday, hour, rain)
    dest_time = get_time(destination_distance, weekday, hour, rain)

    time = []
    time_dif = dest_time - origin_time
    time.append(time_dif)
    conn.close()
    engine.dispose()
    return jsonify(time=time)

# returns information on all stops from origin to destination on a route, for map visualation in index.html


@app.route("/pop_map_route/<int:origin_id>/<int:destination_id>/<jpid>")
@cross_origin()
def get_map_route(origin_id, destination_id, jpid):
    engine = connect_to_database()
    conn = engine.connect()
    stops = []
    o_distance = {}
    d_distance = {}
    o_rows = conn.execute("SELECT position_on_route FROM eta.routes WHERE stop_id = {} AND \
                                    journey_pattern = {}".format(origin_id, "'" + jpid + "'", ))

    d_rows = conn.execute("SELECT position_on_route FROM eta.routes WHERE stop_id = {} AND \
                                    journey_pattern = {}".format(destination_id, "'" + jpid + "'", ))
    for row in o_rows:
        o_distance.update(dict(row))
    for row in d_rows:
        d_distance.update(dict(row))

    rows = conn.execute("SELECT * FROM eta.bus_stops WHERE stop_id IN(SELECT stop_id FROM eta.routes WHERE \
                        position_on_route >= {} and position_on_route <= {} and journey_pattern = {}\
                        ) AND year = 2012".format(o_distance['position_on_route'], d_distance['position_on_route'], "'" + jpid + "'"))

    for row in rows:
        stops.append(dict(row))
    conn.close()
    engine.dispose()
    return jsonify(stops=stops)


@app.route("/first_bus/<int:origin_id>/<int:weekday>/<int:hour>/<int:mins>/<route>")
@cross_origin()
def first_bus_eat(origin_id, weekday, hour, mins, route):
    engine = connect_to_database()
    conn = engine.connect()
    dep_time = []
    jdid_all = []
    route = route[1:4].strip("0")
    origin_distance = 0

    if weekday in range(1, 6):
        workday = 'Workday'
    elif weekday == 6:
        workday = 'Saturday'
    else:
        workday = 'Sunday'
    jpid_list = conn.execute(
        "SELECT DISTINCT journey_pattern FROM timetables_dublin_bus WHERE line = {} ;".format("'" + route + "'"))
    for j in jpid_list:
        jdid_all.append(j['journey_pattern'])
    print(jdid_all)
    jpid = jdid_all[0]
    print(jpid)
    origin_distance_list = conn.execute("SELECT position_on_route FROM routes WHERE stop_id = {} AND \
                                        journey_pattern = {};".format(origin_id, "'" + jpid + "'"))

    d_time = conn.execute("SELECT departure_time FROM timetables_dublin_bus WHERE day_category = {} AND journey_pattern = {};".format(
        "'" + workday + "'", "'" + jpid + "'",))
    print('the depareture_time is ', d_time)
    print('origin_distance_list', origin_distance_list)

    for o in origin_distance_list:
        origin_distance = o['position_on_route']

    for t in d_time:
        dep_time.append(t['departure_time'])

    print("o_distance:", origin_distance)
    print("departure time is :", dep_time)

    if weekday in range(1, 6):
        workday = 0
    else:
        workday = 1

    def get_time(distance, weekday, hour):

        estimated_time = loaded_model_without_weather.predict(
            [distance, hour, weekday])
        return estimated_time[0]

    origin_time = get_time(origin_distance, workday, hour)

    travel_time = timedelta(seconds=int(origin_time))

    print('Travel time to origin stop is ', origin_time)
    begin_time = timedelta(hours=hour, minutes=mins, seconds=0)

    bus_time = []
    for i in dep_time:
        # Parse the time strings
        i += travel_time
        if i > begin_time:
            bus_time.append(i)

    print('arrive times of the bus are ', bus_time)
    First_bus = min(bus_time)
    First_bus = (datetime.min + First_bus).time()

    print("The first bus will arrive at ", First_bus)

    First_bus = str(First_bus)
    print(type(First_bus))

    time = []
    time.append(First_bus)
    conn.close()
    engine.dispose()
    print(time)
    return jsonify(time=time)


@app.route("/timetable/<line_id>")
@cross_origin()
def timetable(line_id):

    engine = connect_to_database()
    conn = engine.connect()
    line_inf = []

    line_query = conn.execute(
        "SELECT * FROM timetables WHERE line = {} ".format("'" + line_id + "'"))

    for i in line_query:
        line_inf.append(dict(i))

    jour_id = {}

    for i in line_inf:
        #m=dict((k, i[k]) for k in ('journey_pattern', 'first_stop', 'last_stop'))
        n = {i['journey_pattern']: [i['first_stop'], i['last_stop']]}
        d_time = i['departure_time']
        d_time = str((datetime.min + d_time).time())
        i['departure_time'] = d_time
        jour_id.update(n)



    for key in jour_id:
        stops = tuple(jour_id[key])
        stop_address = conn.execute(
            "SELECT stop_address FROM eta.bus_stops WHERE year = 2012 AND stop_id in {};".format(stops))
        for s in stop_address:
            jour_id[key].append(s['stop_address'])


    # return line_inf
    return jsonify(line_inf=line_inf, stop_address=jour_id)

