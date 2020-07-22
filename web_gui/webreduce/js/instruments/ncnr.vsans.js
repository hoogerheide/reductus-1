import {extend} from '../libraries.js';
const instrument = {};
export default instrument;

// define the loader and categorizers for ncnr.sans instrument
function load_vsans(load_params, db, noblock, return_type) {
  // load params is a list of: 
  // {datasource: "ncnr", path: "ncnrdata/cgd/...", mtime: 12319123109}
  var noblock = (noblock == true); // defaults to false if not specified
  var return_type = return_type || 'metadata';
  var calc_params = load_params.map(function(lp) {
    return {
      template: {
        "name": "loader_template",
        "description": "VSANS remote loader",
        "modules": [
          {"module": "ncnr.vsans.LoadVSANS", "version": "0.1", "config": {}}
        ],
        "wires": [],
        "instrument": "ncnr.vsans",
        "version": "0.0"
      },
      config: {"0": {"filelist": [{"path": lp.path, "source": lp.source, "mtime": lp.mtime}]}},
      node: 0,
      terminal:  "output",
      return_type: return_type
    }
  });
  return calc_params;
}

var NEXUS_REGEXP = /\.nxs\.[^\.\/]+(\.zip)?$/
var DIV_REGEXP = /DIV\.h5$/

instrument.files_filter = function(x) {
  return (
    ((NEXUS_REGEXP.test(x) || DIV_REGEXP.test(x)) &&
        (/^(fp_)/.test(x) == false) &&
        (/^rapidscan/.test(x) == false) &&
        (/^scripted_findpeak/.test(x) == false))
  )
}

instrument.load_file = load_vsans;
instrument.default_categories = [
  [["analysis.filepurpose"]],
  [["sample.description"]],
  [ 
    [
      "run.instFileNum"
    ],
    [   
      "analysis.intent"
    ]
  ]
];
instrument.categories = extend(true, [], instrument.default_categories);  
  
function add_sample_description(target, file_objs) {
  var jstree = target.jstree(true);
  //var path = webreduce.getCurrentPath(target.parent());
  var to_decorate = jstree.get_json("#", {"flat": true})
    .filter(function(leaf) { 
      return (leaf.li_attr && 
              'filename' in leaf.li_attr &&
              leaf.li_attr.filename in file_objs &&
              'entryname' in leaf.li_attr &&
              'source' in leaf.li_attr &&
              'mtime' in leaf.li_attr) 
      })

  to_decorate.forEach(function(leaf, i) {
    var filename = leaf.li_attr.filename;
    var file_obj = file_objs[filename];
    var entry = file_obj.values.filter(function(f) {return f.entry == leaf.li_attr.entryname});
    if (entry && entry[0]) {
      var e = entry[0];
      if ('sample.description' in e) {
        leaf.li_attr.title = e['sample.description'];
        var parent_id = leaf.parent;
        parent = jstree._model.data[parent_id];
        parent.li_attr.title = e['sample.description'];
      }
    }
  });
}
  
function add_viewer_link(node_list, leaf_list, node_parents, file_objs) {
  const viewer_link = {
    "ncnr": "https://ncnr.nist.gov/ncnrdata/view/nexus-zip-viewer.html",
    "ncnr_DOI": "https://ncnr.nist.gov/ncnrdata/view/nexus-zip-viewer.html",
    "charlotte": "https://charlotte.ncnr.nist.gov/ncnrdata/view/nexus-zip-viewer.html"
  }

  for (let leaf of leaf_list) {
    let fileinfo = leaf.attributes.fileinfo;
    let datasource = fileinfo.source;
    let fullpath = fileinfo.filename;
    if (!(NEXUS_REGEXP.test(fullpath) || NEXUZ_REGEXP.test(fullpath))) {
      continue
    }
    if (viewer_link[datasource]) {
      if (datasource == "ncnr_DOI") { fullpath = "ncnrdata" + fullpath; }
      let pathsegments = fullpath.split("/");
      let pathlist = pathsegments.slice(0, pathsegments.length-1).join("+");
      let filename = pathsegments.slice(-1);
      let viewer = viewer_link[datasource];
      let hdf_or_zip = (NEXUS_REGEXP.test(fullpath) ? viewer.replace("-zip-", "-hdf-") : viewer);
      let link = `<a href="${hdf_or_zip}?pathlist=${pathlist}&filename=${filename}" target="_blank" style="text-decoration:none;">&#9432;</a>`;
      leaf.text += link; 
    }
  }
}
  
instrument.decorators = [add_viewer_link];