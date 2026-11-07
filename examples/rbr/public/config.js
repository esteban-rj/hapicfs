export const STEP_MS=50, ADVANCE_PER_TICK=6, FLOOR_LENGTH=1000, FINISH_DISTANCE=5000, LANE_CHANGE_TICKS=4, INPUT_TTL_MS=350, STUN_TICKS=20;
export const GATES=Object.freeze([[[500,1]],[[300,0],[700,2]],[[250,2],[500,1],[750,0]],[[200,1],[400,0],[600,2],[800,1]],[[160,0],[320,2],[480,1],[640,0],[800,2]]].flatMap((gates,i)=>gates.map(([distance,lane])=>Object.freeze({distance:i*1000+distance,lane}))));
export const floorFor=distance=>Math.min(5,Math.floor(distance/FLOOR_LENGTH)+1);
